#!/usr/bin/env python3
import logging
import argparse
import os
import time
import signal
import sys
import atexit
from pathlib import Path
from threading import Lock
import os.path
import json

# Import modules
from crdl.api import CrunchyrollAPI
from crdl.downloader import CrunchyrollDownloader
from crdl.config import setup_logging
from crdl.media_utils import get_episode_number, format_episode_number
from crdl.version import __version__

# Setup configuration directories
def setup_config_directories():
    """Create configuration directories in user's home folder"""
    # Base config directory
    config_dir = os.path.join(os.path.expanduser("~"), ".config", "crdl")
    
    # Create subdirectories
    json_dir = os.path.join(config_dir, "json")
    widevine_dir = os.path.join(config_dir, "widevine")
    logs_dir = os.path.join(config_dir, "logs")
    
    # Create all directories
    os.makedirs(json_dir, exist_ok=True)
    os.makedirs(widevine_dir, exist_ok=True)
    os.makedirs(logs_dir, exist_ok=True)
    
    return {
        "config_dir": Path(config_dir),
        "json_dir": Path(json_dir),
        "widevine_dir": Path(widevine_dir),
        "logs_dir": Path(logs_dir)
    }

# Create config directories
config_dirs = setup_config_directories()

# Configure logging with new path
logger = setup_logging(config_dirs["logs_dir"])

# Global API instance for proper cleanup
api_instance = None
active_streams = {}
cleanup_lock = Lock()
cleanup_in_progress = False
signal_received = False

# Function to load and save credentials
def save_credentials(username, password):
    """Save credentials to credentials.json"""
    credentials_file = os.path.join(config_dirs["config_dir"], "credentials.json")
    try:
        credentials = {
            "username": username,
            "password": password
        }
        with open(credentials_file, 'w', encoding='utf-8') as f:
            json.dump(credentials, f)
        logger.info("Credentials saved successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to save credentials: {str(e)}")
        return False

def load_credentials():
    """Load credentials from credentials.json"""
    credentials_file = os.path.join(config_dirs["config_dir"], "credentials.json")
    try:
        if os.path.exists(credentials_file):
            with open(credentials_file, 'r', encoding='utf-8') as f:
                credentials = json.load(f)
                return credentials.get("username"), credentials.get("password")
    except Exception as e:
        logger.error(f"Failed to load credentials: {str(e)}")
    return None, None

def cleanup_handler(signum, frame):
    """Handle cleanup when receiving signals"""
    global signal_received
    
    # Only log the first signal
    if not signal_received:
        logger.info(f"Received signal {signum}, exiting gracefully...")
        signal_received = True
    
    # Perform cleanup once
    cleanup_streams()
    
    # Exit without calling sys.exit to allow atexit handlers to run naturally
    os._exit(0)

def cleanup_streams():
    """Clean up any active streams"""
    global api_instance, active_streams, cleanup_in_progress, cleanup_lock
    
    # Use a lock to prevent multiple simultaneous cleanup attempts
    if not cleanup_lock.acquire(blocking=False):
        return  # Cleanup already in progress
        
    try:
        # Check if cleanup already occurred
        if cleanup_in_progress or not api_instance:
            return
            
        # Mark cleanup as started
        cleanup_in_progress = True
            
        # Only log if there are streams to clean up
        if active_streams:
            logger.info("Cleaning up active streams")
            
            # Clean up any tracked active streams
            for guid, token in list(active_streams.items()):
                try:
                    if token:
                        # Only log the first stream deletion to reduce noise
                        suppress = (list(active_streams.keys()).index(guid) > 0)
                        logger.info(f"Deleting stream token for GUID: {guid}")
                        api_instance.delete_streams(guid, token, suppress_errors=suppress)
                except Exception as e:
                    # Only log critical errors
                    logger.error(f"Critical error deleting stream for GUID {guid}: {str(e)}")
            
            # Clear the active streams dictionary
            active_streams.clear()
    
    finally:
        # Release the lock
        cleanup_lock.release()

def register_cleanup_handlers():
    """Register all cleanup handlers"""
    # Register signal handlers
    signal.signal(signal.SIGINT, cleanup_handler)
    signal.signal(signal.SIGTERM, cleanup_handler)
    
    # Register exit handler for normal exits
    atexit.register(cleanup_streams)

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Crunchyroll Downloader')
    
    # Version information
    parser.add_argument('--version', action='store_true', help='Show version information and exit')
    
    # Authentication options
    auth_group = parser.add_argument_group('Authentication')
    auth_group.add_argument('--username', '-u', help='Crunchyroll username')
    auth_group.add_argument('--password', '-p', help='Crunchyroll password')
    
    # Content selection
    content_group = parser.add_argument_group('Content Selection')
    content_group.add_argument('--series', '-s', help='Series ID to download')
    content_group.add_argument('--season', help='Season ID to download')
    content_group.add_argument('--episode', '-e', help='Episode ID to download')
    content_group.add_argument('--locale', default='en-US', help='Content locale (default: en-US)')
    content_group.add_argument('--audio', '-a', default='ja-JP', help='Audio languages to download (comma-separated, e.g., "ja-JP,en-US" or "all")')
    
    # Output options
    output_group = parser.add_argument_group('Output Options')
    output_group.add_argument('--output', '-o', help='Output directory')
    output_group.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    output_group.add_argument('--quality', '-q', choices=['1080p', '720p', 'best', 'worst'], default='1080p', 
                             help='Video quality (1080p, 720p, best, or worst)')
    output_group.add_argument('--release-group', '-r', default='TANMOY', help='Release group name for filename')
    
    return parser.parse_args()

def process_episode(api, downloader, episode_id, locale, cms_data, audio_langs=None, quality=None):
    """Process and download a single episode"""
    global active_streams
    guid = episode_id  # Usually the same for Crunchyroll
    token = None
    
    try:
        # Get episode information
        logger.info(f"Getting information for episode {episode_id}")
        episode = api.get_episode(episode_id, locale, cms_data)
        
        # Get stream information
        logger.info(f"Getting stream information for episode: {episode.get('title', 'Unknown')}")
        streams = api.get_streams(episode_id, locale, cms_data, guid)
        
        if not streams or 'token' not in streams:
            logger.warning(f"No token found in streams response for episode {episode_id}")
            return False
        
        token = streams['token']
        # Track the active stream
        active_streams[guid] = token
        logger.info(f"Received valid stream token for episode {episode_id}")
        
        # Extract stream information
        stream_info = downloader.extract_stream_info(streams)
        if not stream_info:
            logger.error("Failed to extract stream information")
            return False
        
        # Download the episode with audio languages and quality
        logger.info("Starting download process")
        success = downloader.download_episode(stream_info, episode, audio_langs, quality)
        
        if success:
            logger.info(f"Downloaded episode {episode_id} successfully")
        else:
            logger.info(f"Download failed for episode {episode_id}")
        
        return success
        
    except Exception as e:
        logger.error(f"Error processing episode {episode_id}: {str(e)}")
        return False
    finally:
        # Explicitly clean up token only if we're not in the main cleanup process
        # This prevents duplicate cleanup attempts
        if token and guid in active_streams and not cleanup_in_progress:
            try:
                logger.info(f"Cleaning up token for episode {episode_id}")
                api.delete_streams(guid, token)
                # Remove from active streams
                if guid in active_streams:
                    del active_streams[guid]
            except Exception as e:
                logger.error(f"Failed to delete stream token for {episode_id}: {str(e)}")

def process_season(api, downloader, season_id, locale, cms_data, audio_langs=None, quality=None):
    """Process and download all episodes in a season"""
    logger.info(f"Getting episodes for season {season_id}")
    episodes = api.get_episodes(season_id, locale, cms_data)
    
    results = []
    
    # Get all episode IDs first
    episode_ids = []
    for episode_item in episodes.get('items', []):
        episode_id = episode_item.get('id')
        if episode_id:
            episode_ids.append((episode_id, episode_item.get('title', 'Unknown')))
    
    logger.info(f"Found {len(episode_ids)} episodes to process")
    
    # Process one episode at a time
    for i, (episode_id, title) in enumerate(episode_ids):
        logger.info(f"Processing episode {i+1}/{len(episode_ids)}: {title} ({episode_id})")
        
        # Small delay between episodes to avoid rate limiting
        if i > 0:
            time.sleep(3)
        
        try:
            # Get detailed episode information
            episode = api.get_episode(episode_id, locale, cms_data)
            
            # Process this episode with quality setting
            success = process_episode(api, downloader, episode_id, locale, cms_data, audio_langs, quality)
            
            if success:
                logger.info(f"Successfully downloaded episode: {episode.get('title', 'Unknown')}")
            
            results.append((episode_id, success))
            
        except Exception as e:
            logger.error(f"Error processing episode {episode_id}: {str(e)}")
            results.append((episode_id, False))
            
            # Add cooldown only after consecutive failures
            consecutive_failures = sum(1 for r in results[-2:] if not r[1]) if len(results) >= 2 else 0
            if consecutive_failures >= 2:
                logger.warning("Multiple consecutive failures. Adding short cooldown.")
                time.sleep(15)
    
    return results

def display_seasons(seasons):
    """Display available seasons"""
    print("\n=== Seasons ===")
    for i, season in enumerate(seasons.get('items', []), 1):
        print(f"{i}. {season.get('title', 'Unknown Season')} (ID: {season.get('id')})")

def display_episodes(episodes):
    """Display available episodes"""
    print("\n=== Episodes ===")
    for i, episode in enumerate(episodes.get('items', []), 1):
        print(f"{i}. {episode.get('title', 'Unknown')} (Episode {episode.get('episode_number', '?')}) (ID: {episode.get('id')})")

def display_series_info(series_title, sorted_season_items, season_episode_counts, total_episodes):
    """Display formatted series information with seasons and episodes"""
    print(f"\n=== Series: {series_title} ===")
    print(f"Total unique seasons: {len(sorted_season_items)}")
    print(f"\nFound {total_episodes} total episodes across all seasons:")
    
    for i, season in enumerate(sorted_season_items):
        season_id = season.get('id')
        season_number = season.get('season_number')
        season_title = season.get('title', 'Unknown')
        episode_count = season_episode_counts[season_id]['count']
        print(f"{i+1}. Season {season_number}: {season_title} ({episode_count} episodes)")
        
        # Display episode information
        episodes = season_episode_counts[season_id]['episodes']
        if not episodes:
            print("   No episodes found for this season")
            continue
        
        print("   Episodes:")
        for j, episode in enumerate(episodes):
            # Use the utility function to get consistent episode numbering
            ep_num = get_episode_number(episode)
            ep_title = episode.get('title', 'Unknown')
            ep_id = episode.get('id')
            print(f"   {j+1}. Episode {ep_num}: {ep_title} (ID: {ep_id})")

def get_season_episodes(api, sorted_season_items, locale, cms_data):
    """Get episode information for all seasons"""
    season_episode_counts = {}
    total_episodes = 0
    
    print("\nGetting episode information for each season...")
    for season in sorted_season_items:
        season_id = season.get('id')
        # Get episode count for this season
        try:
            episodes = api.get_episodes(season_id, locale, cms_data)
            episode_count = len(episodes.get('items', []) if episodes else [])
            season_episode_counts[season_id] = {
                'count': episode_count,
                'episodes': episodes.get('items', []) if episodes else []
            }
            total_episodes += episode_count
        except Exception as e:
            logger.error(f"Error getting episodes for season {season.get('title')}: {str(e)}")
            season_episode_counts[season_id] = {'count': 0, 'episodes': []}
    
    return season_episode_counts, total_episodes

def filter_unique_seasons(seasons):
    """Filter out duplicate seasons based on identifier"""
    unique_seasons = {}
    
    # Group seasons by their identifier (e.g., "G4PH0WXVJ|S1", "G4PH0WXVJ|S2")
    for season in seasons.get('items', []):
        identifier = season.get('identifier')
        if not identifier:
            continue
        
        # Check if we already have a season with this identifier
        if identifier not in unique_seasons:
            unique_seasons[identifier] = season
            continue
            
        # Prioritize non-dubbed versions (original Japanese)
        if not unique_seasons[identifier].get('is_dubbed') and season.get('is_dubbed'):
            unique_seasons[identifier] = season
            continue
            
        # Check for original Japanese audio version
        if 'versions' in season:
            for version in season.get('versions', []):
                if version.get('original') is True and version.get('audio_locale') == 'ja-JP':
                    unique_seasons[identifier] = season
                    break
    
    # Create a sorted list of unique seasons
    sorted_season_items = sorted(
        unique_seasons.values(), 
        key=lambda s: (s.get('season_number', 0), s.get('identifier', ''))
    )
    
    return sorted_season_items

def download_all_seasons(api, downloader, sorted_season_items, locale, cms_data, audio_langs=None, quality=None):
    """Download all seasons in sequence"""
    total_episodes_downloaded = 0
    total_episodes_failed = 0
    
    for i, season in enumerate(sorted_season_items):
        season_id = season.get('id')
        season_number = season.get('season_number')
        logger.info(f"Processing season {i+1}/{len(sorted_season_items)}: {season.get('title', 'Unknown')} (Season {season_number})")
        
        # Get episodes for this season
        episodes = api.get_episodes(season_id, locale, cms_data)
        
        if not episodes or not episodes.get('items'):
            logger.warning(f"No episodes found for season {season.get('title')}. Skipping to next season.")
            continue
        
        episode_count = len(episodes.get('items', []))
        logger.info(f"Found {episode_count} episodes in this season")
        
        # Download all episodes in this season
        logger.info(f"Downloading all episodes in season {i+1}: {season.get('title', 'Unknown')}")
        results = process_season(api, downloader, season_id, locale, cms_data, audio_langs, quality)
        
        # Count successes and failures
        successes = sum(1 for r in results if r[1])
        failures = sum(1 for r in results if not r[1])
        
        logger.info(f"Season {i+1} download completed. Successfully downloaded {successes} episodes. Failed to download {failures} episodes.")
        
        total_episodes_downloaded += successes
        total_episodes_failed += failures
        
        # Add a small delay between seasons to avoid rate limiting
        if i < len(sorted_season_items) - 1:
            logger.info("Waiting 5 seconds before starting the next season...")
            time.sleep(5)
    
    logger.info(f"All seasons downloaded. Total: {total_episodes_downloaded} episodes downloaded, {total_episodes_failed} failed.")
    return total_episodes_downloaded, total_episodes_failed

def process_series(api, downloader, series_id, locale, cms_data, audio_langs=None, quality=None):
    """Process a series, show information and download if confirmed"""
    logger.info(f"Getting information for series {series_id}")
    series = api.get_series(series_id, locale, cms_data)
    
    if not series:
        logger.error(f"Series with ID {series_id} not found.")
        return False
    
    series_title = series.get('title', 'Unknown')
    logger.info(f"Series title: {series_title}")
    logger.info("Getting seasons for the series")
    
    seasons = api.get_seasons(series_id, locale, cms_data)
    if not seasons or not seasons.get('items'):
        logger.error("No seasons found for this series.")
        return False
    
    # Filter out duplicate seasons
    sorted_season_items = filter_unique_seasons(seasons)
    logger.info(f"Found {len(seasons.get('items', []))} total seasons (including dubs)")
    logger.info(f"Identified {len(sorted_season_items)} unique seasons")
    
    # Get and display episode information
    season_episode_counts, total_episodes = get_season_episodes(api, sorted_season_items, locale, cms_data)
    display_series_info(series_title, sorted_season_items, season_episode_counts, total_episodes)
    
    # Ask for user confirmation before downloading
    confirm = input(f"\nDo you want to download the whole series ({total_episodes} episodes)? (y/n): ").strip().lower()
    if confirm not in ('y', 'yes'):
        print("Download canceled.")
        return False
    
    print(f"Starting download of all seasons for {series_title}...")
    download_all_seasons(api, downloader, sorted_season_items, locale, cms_data, audio_langs, quality)
    return True

def main():
    """Main application entry point"""
    args = parse_arguments()
    
    # Show version information if requested
    if args.version:
        print(f"Crunchyroll Downloader v{__version__}")
        return
    
    # Set log level
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    
    # Try to get credentials
    username = args.username
    password = args.password
    
    # If not provided in command line, try to load from file
    if not username or not password:
        loaded_username, loaded_password = load_credentials()
        
        # Use loaded credentials if available
        if loaded_username and loaded_password:
            logger.info("Using saved credentials")
            username = loaded_username
            password = loaded_password
        else:
            logger.error("No credentials provided. Use --username and --password arguments or save credentials.")
            return
    else:
        # Save provided credentials for future use
        save_credentials(username, password)
    
    # Initialize the API client with config directories
    api = CrunchyrollAPI(username, password, config_dirs=config_dirs)
    global api_instance
    api_instance = api  # Store in global variable for signal handlers
    downloader = None
    
    try:
        # Login to Crunchyroll
        if not api.login():
            logger.error("Failed to login. Exiting.")
            return
        
        # Verify the token is valid
        if not api.check_token_valid():
            logger.error("Initial token validation failed. Exiting.")
            return
        
        # Get user profile
        profile = api.get_profile()
        logger.info(f"Logged in as: {profile.get('username', profile.get('email', 'Unknown'))}")
        
        # Get account information
        accounts = api.get_accounts()
        logger.info(f"Account ID: {api.account_id}, External ID: {api.external_id}")
        
        # Get subscription information
        api.get_subscription()
        
        # Get CMS index information
        index = api.get_index()
        cms_data = index.get('cms', {})
        
        # Set the output directory
        output_dir = args.output
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            download_dir = Path(output_dir)
        else:
            # Use the configured output directory
            download_dir = api.config.output_dir
        
        # Create config for the downloader
        config = {
            'release_group': args.release_group,
            'default_quality': args.quality,
            'widevine_dir': config_dirs["widevine_dir"]
        }
        
        # Initialize the downloader with configuration
        downloader = CrunchyrollDownloader(api, download_dir, config)
        
        # Register cleanup handlers after initialization
        register_cleanup_handlers()
        
        # Check required parameters
        if args.episode:
            # Process single episode
            if not process_episode(api, downloader, args.episode, args.locale, cms_data, args.audio, args.quality):
                logger.error(f"Failed to process episode {args.episode}")
        elif args.season:
            # Process single season
            if not process_season(api, downloader, args.season, args.locale, cms_data, args.audio, args.quality):
                logger.error(f"Failed to process season {args.season}")
        elif args.series:
            # Process entire series
            if not process_series(api, downloader, args.series, args.locale, cms_data, args.audio, args.quality):
                logger.error(f"Failed to process series {args.series}")
        else:
            # No content selected
            logger.error("No content selected. You must specify --episode, --season, or --series.")
            return
            
        logger.info("All tasks completed")
        
    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
        # Cleanup will be handled by the signal handler
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}", exc_info=True)
    finally:
        # Perform cleanup if not already done
        cleanup_streams()

if __name__ == '__main__':
    main()

