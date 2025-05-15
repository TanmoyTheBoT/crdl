"""Crunchyroll downloader module"""
import json
import logging
import os
import re
import subprocess
import base64
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
import cloudscraper

from .api import CrunchyrollAPI
from .config import save_json, CrunchyrollConfig
from .drm_utils import decode_pssh, extract_mpd_info, create_pssh_object, get_license_from_response
from .media_utils import (download_subtitles, extract_chapter_info, 
                         extract_metadata, construct_filename, 
                         clean_temp_files, mux_media_files, construct_series_folder_name, construct_season_folder_name)

logger = logging.getLogger("CrunchyrollDownloader")

class CrunchyrollDownloader:
    """Handles downloading and DRM processing for Crunchyroll content"""
    
    def __init__(self, api: CrunchyrollAPI, output_dir: Path = None, config: Dict = None):
        """
        Initialize the downloader
        
        Args:
            api: Authenticated CrunchyrollAPI instance
            output_dir: Directory to save downloaded content
            config: Optional configuration dictionary for filenames
        """
        self.api = api
        # Create output directory for saved content if it doesn't exist
        self.output_dir = output_dir or Path('downloads')
        self.output_dir.mkdir(exist_ok=True)
        
        # Use JSON directory from API configuration (already created)
        self.json_dir = self.api.json_dir
        
        # Store configuration for filenames
        self.config = config or {}
    
    def extract_stream_info(self, streams_data: Dict) -> Optional[Dict]:
        """
        Extract stream information including MPD URL from the streams response
        
        Args:
            streams_data: JSON response from the streams API
            
        Returns:
            Optional[Dict]: Dictionary containing stream information including URLs and DRM info
        """
        try:
            # Check if streams data is valid
            if not streams_data:
                logger.error("Empty streams data received")
                return None
                
            if 'error' in streams_data:
                logger.error(f"Error in streams data: {streams_data.get('error')}")
                return None
            
            # Get the MPD URL - check both formats (hardSubs and direct url)
            mpd_url = None
            
            # First check for direct URL field (new format)
            if 'url' in streams_data and streams_data['url']:
                mpd_url = streams_data['url']
                logger.info("Found direct MPD URL in streams response")
            else:
                # Check for hardSubs (old format)
                hard_subs = streams_data.get('hardSubs', {})
                if hard_subs:
                    # Get the first available MPD URL (using en-US as default)
                    if 'en-US' in hard_subs:
                        mpd_url = hard_subs['en-US'].get('url')
                    else:
                        # If en-US not available, use the first available language
                        first_lang = next(iter(hard_subs))
                        mpd_url = hard_subs[first_lang].get('url')
                        
                    logger.info(f"Found MPD URL in hardSubs ({first_lang if 'en-US' not in hard_subs else 'en-US'})")
                    
            if not mpd_url:
                logger.error("No MPD URL found in streams response")
                return None
            
            # Get the video token
            video_token = streams_data.get("token")
            if not video_token:
                logger.warning("No video token found in streams response")
            
            # Parse the MPD to get DRM information
            drm_info = self.parse_mpd(mpd_url, video_token)
            
            if not drm_info:
                logger.error("Failed to extract DRM information from MPD")
                return {
                    "mpd_url": mpd_url,
                    "pssh": None,
                    "kid": None,
                    "license_url": None,
                    "video_token": video_token
                }
            
            # Get subtitles if available
            subtitles = streams_data.get("subtitles", {})
            if subtitles:
                logger.info(f"Found {len(subtitles)} subtitle tracks in streams response")
            
            # Get the license key if PSSH is available
            if drm_info.get("pssh") and drm_info.get("license_url"):
                logger.info("PSSH and license URL available, getting license key")
                keys = self.get_license_key(
                    drm_info["license_url"],
                    drm_info["pssh"],
                    video_token,
                    mpd_url,
                    "video"
                )
                
                if keys:
                    logger.info(f"Successfully retrieved {len(keys)} keys")
                    drm_info["keys"] = keys
                else:
                    logger.warning("Failed to retrieve license keys")
            
            stream_info = {
                "mpd_url": mpd_url,
                "pssh": drm_info.get("pssh"),
                "kid": drm_info.get("kid"),
                "license_url": drm_info.get("license_url"),
                "video_token": video_token,
                "keys": drm_info.get("keys"),
                "subtitles": subtitles
            }
            
            # Save the DRM information to a JSON file
            save_json(stream_info, 'drm_info.json', self.json_dir)
            
            return stream_info
        
        except Exception as e:
            logger.error(f"Error extracting stream info: {str(e)}", exc_info=True)
            return None

    def parse_mpd(self, mpd_url, video_token=None):
        """
        Parse MPD file to extract important DRM information
        
        Args:
            mpd_url: URL to the MPD file
            video_token: Video token for authentication
            
        Returns:
            dict: Dictionary containing DRM info (PSSH, KID, license URL)
        """
        try:
            logger.info(f"Downloading MPD: {mpd_url}")
            
            # Download the MPD file
            headers = {
                'User-Agent': self.api.config.USER_AGENT,
                'Origin': 'https://static.crunchyroll.com',
                'Referer': 'https://static.crunchyroll.com/'
            }
            
            if self.api.access_token:
                headers['Authorization'] = f'Bearer {self.api.access_token}'
            
            if video_token:
                headers['X-Cr-Video-Token'] = video_token
            
            response = requests.get(mpd_url, headers=headers)
            if response.status_code != 200:
                logger.error(f"Failed to download MPD: {response.status_code}")
                return None
            
            mpd_content = response.text
            
            # Save raw MPD for debugging
            try:
                mpd_filename = f"mpd_{int(time.time())}.xml"
                with open(self.json_dir / mpd_filename, 'w') as f:
                    f.write(mpd_content)
                logger.info(f"Saved MPD content to {mpd_filename}")
            except:
                pass
                
            # Extract DRM information using our utility
            drm_info = extract_mpd_info(mpd_content)
            
            # If we extracted info, log it for easier debugging
            if drm_info:
                logger.info(f"Successfully extracted DRM info from MPD:")
                if drm_info.get('pssh'):
                    logger.info(f"  PSSH: {drm_info['pssh']}")
                if drm_info.get('kid'):
                    logger.info(f"  KID: {drm_info['kid']}")
                if drm_info.get('license_url'):
                    logger.info(f"  License URL: {drm_info['license_url']}")
            else:
                logger.warning(f"Failed to extract DRM info from MPD, falling back to default values")
                
                # Try to extract just license URL if nothing else worked
                license_url = None
                try:
                    import xml.etree.ElementTree as ET
                    root = ET.fromstring(mpd_content)
                    ns = {'ns': 'urn:mpeg:dash:schema:mpd:2011'}
                    contentprotection = root.findall('.//ns:ContentProtection', ns)
                    for cp in contentprotection:
                        if 'cenc:default_KID' in cp.attrib:
                            default_kid = cp.attrib['cenc:default_KID'].replace('-', '').lower()
                            logger.info(f"Found KID in MPD: {default_kid}")
                            license_url = "https://cr-license-proxy.prd.crunchyrollsvc.com/v1/license/widevine"
                            return {
                                "kid": default_kid,
                                "license_url": license_url
                            }
                except Exception as e:
                    logger.error(f"Error trying to extract basic license info: {str(e)}")
                
            return drm_info
            
        except Exception as e:
            logger.error(f"Error parsing MPD: {str(e)}", exc_info=True)
            return None

    def _get_cloudscraper_session(self):
        """
        Get a cloudscraper session for bypassing Cloudflare
        
        Returns:
            cloudscraper.CloudScraper: Session with Cloudflare bypass
        """
        try:
            
            scraper = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'windows',
                    'desktop': True,
                    'mobile': False
                },
                delay=8,
                interpreter='js2py',
                allow_brotli=True,
                cipherSuite='ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:ECDHE-RSA-AES128-SHA:ECDHE-RSA-AES256-SHA:AES128-GCM-SHA256:AES256-GCM-SHA384:AES128-SHA:AES256-SHA'
            )
            
            # Set basic headers
            scraper.headers.update({
                'User-Agent': CrunchyrollConfig.USER_AGENT_PC,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1'
            })
            
            # Add cookies from API if available
            if self.api.cookies:
                for cookie in self.api.cookies:
                    scraper.cookies.set(cookie.name, cookie.value)
                    
            logger.info("Created CloudScraper session for Cloudflare bypass")
            return scraper
        except Exception as e:
            logger.error(f"Failed to create CloudScraper session: {str(e)}")
            # Fallback to regular requests session
            logger.warning("Falling back to regular requests session")
            return requests.Session()
            
    def get_license_key(self, license_url, pssh, video_token=None, mpd_url=None, stream_type="video"):
        """
        Get the content decryption key from the license server
        
        Args:
            license_url: URL of the license server
            pssh: PSSH box in base64 format
            video_token: Video token for authentication
            mpd_url: URL of the MPD file (used for asset ID extraction)
            stream_type: Type of stream ("video" or "audio") for better logging
            
        Returns:
            list: List of content keys
        """
        try:
            logger.info(f"Getting license key for {stream_type.upper()} stream")
            logger.info(f"PSSH: {pssh}")
            logger.info(f"License URL: {license_url}")
            
            # Initialize PyWidevine CDM
            try:
                from pywidevine.cdm import Cdm
                from pywidevine.device import Device
                from pywidevine.pssh import PSSH
            except ImportError:
                logger.error("Failed to import pywidevine modules. Please install them first.")
                return None
            
            # Get widevine device path from configuration
            widevine_path = self.config.get('widevine_dir') / 'device.wvd'
            
            try:
                logger.info(f"Loading Widevine device from {widevine_path}")
                device = Device.load(widevine_path)
                if not device:
                    logger.error(f"Failed to load Widevine device from {widevine_path}")
                    return None
                logger.info(f"Successfully loaded Widevine device")
            except Exception as e:
                logger.error(f"Could not load Widevine device: {str(e)}")
                return None
            
            cdm = Cdm(
                device.type,
                device.system_id,
                device.security_level,
                device.client_id,
                device.private_key
            )
            
            # Create a session for the PSSH
            session_id = cdm.open()
            
            # Create a PSSH object from the base64 string
            try:
                # Create proper PSSH object instead of using raw string
                pssh_obj = PSSH(pssh)
                logger.info(f"Successfully created PSSH object with KID: {pssh_obj.key_ids[0].hex() if pssh_obj.key_ids else 'unknown'}")
                
                # Prepare license challenge
                challenge = cdm.get_license_challenge(session_id, pssh_obj)
            except Exception as e:
                logger.error(f"Error creating PSSH object: {str(e)}")
                # Try alternative approach - create a custom PSSH object
                try:
                    logger.info("Trying alternative approach to create PSSH object")
                    # Extract the KID from decoded PSSH
                    kid_info = decode_pssh(pssh)
                    if kid_info and kid_info.get('kid'):
                        kid_hex = kid_info['kid']
                        logger.info(f"Creating PSSH object with KID: {kid_hex}")
                        
                        # Use the helper function to create a PSSH object
                        pssh_obj = create_pssh_object(pssh_base64=pssh, kid_hex=kid_hex)
                        
                        if not pssh_obj:
                            logger.error("Failed to create PSSH object using all methods")
                            return None
                        
                        logger.info("Successfully created PSSH object")
                        challenge = cdm.get_license_challenge(session_id, pssh_obj)
                    else:
                        logger.error("Could not extract KID from PSSH")
                        return None
                except Exception as e2:
                    logger.error(f"Alternative PSSH creation also failed: {str(e2)}")
                    return None
            
            # Extract asset_id from MPD URL if available
            asset_id = None
            if mpd_url:
                # Extract asset ID using regex pattern
                asset_id_match = re.search(r'/assets/(?:p/)?([^_,]+)', mpd_url)
                if asset_id_match:
                    asset_id = asset_id_match.group(1)
                    logger.info(f"Extracted asset_id: {asset_id}")

            # Go directly to Crunchyroll license request
            license_acquired = False
            license_res = None
            
            # Create a cloudscraper session for Cloudflare bypass
            scraper = self._get_cloudscraper_session()
            
            # Direct Crunchyroll license request
            logger.info("Making direct license request to Crunchyroll")
            
            # Use the license URL from config or the one provided
            license_url = license_url or self.api.config.LICENSE_URL 
            logger.info(f"Using license URL: {license_url}")
            
            # Extract media ID from episode
            media_id = None
            if mpd_url:
                # Try to extract media ID for content-id header
                media_id_match = re.search(r'/([^/]+)/evs', mpd_url)
                if media_id_match:
                    media_id = media_id_match.group(1)
                    logger.info(f"Extracted media_id: {media_id}")
            
            
            headers = {
                'Content-Type': 'application/octet-stream',
                'User-Agent': CrunchyrollConfig.USER_AGENT_PC,
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Origin': 'https://static.crunchyroll.com',
                'Referer': 'https://static.crunchyroll.com/',
                'Connection': 'keep-alive',
                'X-Cr-Content-Type': 'mp4',
                'Sec-Ch-Ua': '"Chromium";v="129", "Google Chrome";v="129", "Not?A_Brand";v="24"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"Windows"'
            }
            
            # Add content-id header if we have a media ID
            if media_id:
                headers['X-Cr-Content-Id'] = media_id
            
            # Add video token if available
            if video_token:
                headers['X-Cr-Video-Token'] = video_token
            
            # Add authorization header if available
            if self.api.access_token:
                headers['Authorization'] = f'Bearer {self.api.access_token}'
            
            try:
                # Create a new CloudScraper session for each attempt to avoid stale cookies/headers
                license_scraper = cloudscraper.create_scraper(
                    browser={
                        'browser': 'chrome',
                        'platform': 'windows',
                        'version': '129.0.0.0',
                        'desktop': True,
                        'mobile': False
                    },
                    delay=8,
                    interpreter='js2py',
                    allow_brotli=True,
                    cipherSuite='ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384'
                )
                
                # Set all headers for this specific request
                for header, value in headers.items():
                    license_scraper.headers[header] = value
                
                # Make the license request
                logger.info(f"Making license request to: {license_url}")
                logger.info(f"Using headers: {license_scraper.headers}")
                
                # Add cookies from API
                if self.api.cookies:
                    for cookie in self.api.cookies:
                        license_scraper.cookies.set(cookie.name, cookie.value)
                
                response = license_scraper.post(
                    license_url, 
                    data=challenge,
                    timeout=30  # Increase timeout for CF challenge
                )
                
                if response.status_code == 200:
                    license_acquired = True
                    # Process the license response - extract from JSON if needed
                    license_res = get_license_from_response(response.content)
                    logger.info("Direct license request successful with CloudScraper!")
                else:
                    logger.error(f"Direct license request with CloudScraper failed with status code: {response.status_code}")
                    logger.error(f"Response text: {response.text[:500]}")
            except Exception as e:
                logger.error(f"Error using CloudScraper for license request: {str(e)}", exc_info=True)
                
            if not license_acquired or license_res is None:
                logger.error("License acquisition failed")
                return None
            
            logger.info("License acquired, parsing response")
            cdm.parse_license(session_id, license_res)
            
            # Get the content keys
            keys = cdm.get_keys(session_id)
            cdm.close(session_id)
            
            # Format the keys
            key_list = []
            mp4decrypt_format = []
            for key in keys:
                try:
                    # Handle key.kid as either bytes or UUID
                    if hasattr(key.kid, 'bytes'):
                        # For PyWidevine 1.8.0, key.kid is a UUID object
                        key_id_hex = key.kid.bytes.hex()
                    elif isinstance(key.kid, bytes):
                        # For older versions, key.kid is a bytes object
                        key_id_hex = key.kid.hex()
                    else:
                        # Convert string representation of UUID to bytes
                        key_id_hex = str(key.kid).replace('-', '')
                    
                    # Handle key.key as either bytes or another format
                    if isinstance(key.key, bytes):
                        key_hex = key.key.hex()
                    elif hasattr(key.key, 'bytes'):
                        # For UUID type keys
                        key_hex = key.key.bytes.hex()
                    else:
                        # Try to convert to string and clean up
                        key_hex = str(key.key).replace('-', '')
                    
                    key_type = key.type
                    logger.info(f"Key ID: {key_id_hex}, Key: {key_hex}, Type: {key_type}")
                    key_list.append({
                        "key_id": key_id_hex,
                        "key": key_hex,
                        "type": key_type
                    })
                    # Format for MP4Decrypt: --key KID:KEY
                    mp4decrypt_format.append(f"--key {key_id_hex}:{key_hex}")
                except Exception as e:
                    logger.error(f"Error processing key: {str(e)}")
            
            # Write the keys to a JSON file
            save_json(key_list, 'keys.json', self.json_dir)
            
            # Write keys in MP4Decrypt format
            with open(self.json_dir / 'mp4decrypt_keys.txt', 'w') as f:
                f.write(' '.join(mp4decrypt_format))
                
            return key_list
            
        except Exception as e:
            logger.error(f"Error getting license key: {str(e)}", exc_info=True)
            return None

    def download_episode(self, stream_info: Dict, episode_data: Dict, audio_langs: str = None, quality: str = None) -> bool:
        """
        Download an episode using N_m3u8DL-RE
        
        Args:
            stream_info: Stream information including MPD URL and keys
            episode_data: Episode metadata
            audio_langs: Comma-separated list of audio languages to download (e.g., "ja-JP,en-US") or "all"
            quality: Video quality setting (1080p, 720p, best, worst)
            
        Returns:
            bool: True if download was successful, False otherwise
        """
        try:
            # Get the keys from stream_info or fetch them if not present
            keys = stream_info.get('keys')
            if not keys and stream_info.get('pssh') and stream_info.get('license_url'):
                logger.info("Keys not found in stream_info, fetching them...")
                keys = self.get_license_key(
                    stream_info['license_url'],
                    stream_info['pssh'],
                    stream_info['video_token'],
                    stream_info['mpd_url'],
                    "video"
                )
                if keys:
                    # Update stream_info with the keys
                    stream_info['keys'] = keys
                    save_json(stream_info, 'drm_info.json', self.json_dir)
            
            # Extract episode information for filename
            try:
                # Extract metadata
                metadata = extract_metadata(episode_data)
                
                # Set quality in metadata if specified
                if quality and quality not in ['best', 'worst']:
                    metadata['quality'] = quality
                
                # Create config with quality
                filename_config = self.config.copy()
                if quality and quality not in ['best', 'worst']:
                    filename_config['default_quality'] = quality
                
                # Build filename with config
                filename = construct_filename(metadata, filename_config)
                logger.info(f"Saving file as: {filename}")
            except Exception as e:
                # Fallback filename if something goes wrong
                filename = f"Crunchyroll_Episode_S01E01_1080p"
                logger.error(f"Error creating filename: {str(e)}", exc_info=True)
                logger.info(f"Using default filename: {filename}")
            
            # Check if N_m3u8DL-RE is available
            try:
                subprocess.run(["N_m3u8DL-RE", "--version"], capture_output=True, text=True)
                logger.info("N_m3u8DL-RE is available")
            except FileNotFoundError:
                logger.error("N_m3u8DL-RE not found. Please install it and make sure it's in your PATH.")
                return False
            
            # Start the download
            logger.info(f"Starting download with N_m3u8DL-RE...")
            
            try:
                episode_id = episode_data.get('id')
                series_id = episode_data.get('series_id')
                series_data = None
                
                # Try to get series data to extract all seasons information
                if series_id:
                    try:
                        # Get fresh CMS data for the series request
                        index = self.api.get_index()
                        cms_data = index.get('cms', {})
                        
                        # Get detailed series information including seasons
                        logger.info(f"Getting series data for folder structure: {series_id}")
                        series_data = self.api.get_series(series_id, 'en-US', cms_data)
                        
                        if series_data:
                            logger.info(f"Successfully retrieved series data with {len(series_data.get('seasons', []))} seasons")
                        else:
                            logger.warning("Failed to get series data, using single season folder")
                    except Exception as e:
                        logger.error(f"Error fetching series data: {str(e)}")
                
                # Create main series directory with simpler format
                series_folder_name = construct_series_folder_name(
                    metadata['series_title'], 
                    metadata['season_number'],
                    metadata['quality'],
                    series_data,
                    filename_config
                )
                output_dir = self.output_dir / series_folder_name
                output_dir.mkdir(exist_ok=True)
                
                # Create season folder with the requested format
                season_folder = construct_season_folder_name(
                    metadata['series_title'],
                    metadata['season_number'],
                    metadata['quality'],
                    filename_config
                )
                season_output_dir = output_dir / season_folder
                season_output_dir.mkdir(exist_ok=True)
                
                # Extract chapter information if available
                chapter_file = extract_chapter_info(episode_data, episode_id, season_output_dir)
                if chapter_file:
                    logger.info(f"Generated chapter file: {chapter_file}")
                
                # Set working directory to the season output directory
                cwd = str(season_output_dir)
                
                # STEP 1: DOWNLOAD VIDEO ONLY
                logger.info("STEP 1: DOWNLOADING VIDEO TRACK")
                
                # First download video only
                video_download_cmd = [
                    "N_m3u8DL-RE", 
                    stream_info['mpd_url'],
                    "--header", f"accept-language: en-US,en;q=0.9",
                    "--header", f"authorization: Bearer {self.api.access_token}",
                    "--header", "content-type: application/octet-stream",
                    "--header", "referer: https://static.crunchyroll.com/",
                    "--header", f"user-agent: {self.api.config.USER_AGENT}",
                    "--header", f"x-cr-content-id: {episode_id}",
                    "--binary-merge", "false",     
                    "--save-name", f"{filename}_video",
                    "--drop-audio", ".*",      # Drop all audio streams
                    "--drop-subtitle", ".*"    # Drop all subtitles from the stream
                ]
                
                # Add video quality parameter based on quality setting
                if quality:
                    if quality == "1080p":
                        video_download_cmd.extend(["-sv", 'res="1080*"'])
                        logger.info("Using 1080p video quality")
                    elif quality == "720p":
                        video_download_cmd.extend(["-sv", 'res="720*"'])
                        logger.info("Using 720p video quality")
                    elif quality == "best":
                        video_download_cmd.extend(["-sv", "best"])
                        logger.info("Using best available video quality")
                    elif quality == "worst":
                        video_download_cmd.extend(["-sv", "worst"])
                        logger.info("Using lowest video quality")
                else:
                    # Default to 1080p if no quality specified
                    video_download_cmd.extend(["-sv", 'res="1080*"'])
                    logger.info("Using default 1080p video quality")
                
                # Add video token if available for video download
                if stream_info.get('video_token'):
                    video_download_cmd.extend(["--header", f"x-cr-video-token: {stream_info['video_token']}"])
                
                # Add video decryption key if available
                if keys:
                    logger.info("Adding decryption key to video download command")
                    
                    # Find a CONTENT type key
                    content_key = None
                    for key in keys:
                        if key.get('type') == 'CONTENT':
                            content_key = key
                            break
                    
                    if not content_key:
                        # If no CONTENT type key, use the first key
                        content_key = keys[0]
                    
                    key_param = f"{content_key['key_id']}:{content_key['key']}"
                    logger.info(f"Using key for video decryption: {key_param}")
                    video_download_cmd.extend(["--key", key_param])
                else:
                    logger.warning("No keys available for video download, attempting without decryption (may fail for DRM content)")
                
                # Run the video download command
                logger.info(f"Running video download command in directory: {cwd}")
                logger.info(f"Command: {' '.join(video_download_cmd)}")
                
                video_result = subprocess.run(video_download_cmd, cwd=cwd)
                if video_result.returncode != 0:
                    logger.error(f"Video download failed with return code: {video_result.returncode}")
                    return False
                
                logger.info("Video downloaded successfully")
                
                # Close the video stream before downloading audio
                if stream_info.get('video_token'):
                    logger.info(f"Closing stream after video download")
                    self.api.delete_streams(episode_id, stream_info['video_token'])
                
                # STEP 2: DOWNLOAD AUDIO TRACKS BY LANGUAGE
                logger.info("STEP 2: DOWNLOADING AUDIO TRACKS BY LANGUAGE")
                
                # Parse audio language flag (default: ja-JP)
                audio_langs_list = ['ja-JP']  # Default is Japanese
                
                # Process the audio_langs parameter if provided
                if audio_langs:
                    if audio_langs.lower() == "all":
                        # Get all available audio language codes
                        audio_langs_list = []
                        if 'versions' in episode_data:
                            for version in episode_data.get('versions', []):
                                if version.get('audio_locale'):
                                    audio_langs_list.append(version.get('audio_locale'))
                        
                        if not audio_langs_list:  # If no versions found, default to Japanese
                            audio_langs_list = ['ja-JP']
                            
                        logger.info(f"Set to download ALL audio languages: {audio_langs_list}")
                    else:
                        # Parse comma-separated language codes
                        audio_langs_list = [lang.strip() for lang in audio_langs.split(',')]
                        logger.info(f"Set to download specific audio languages: {audio_langs_list}")
                
                # Get fresh CMS data for stream requests
                index = self.api.get_index()
                cms_data = index.get('cms', {})
                
                # Find audio version GUIDs for each requested language
                audio_files = []
                audio_languages = []
                original_audio_index = -1
                
                for i, audio_lang in enumerate(audio_langs_list):
                    audio_guid = None
                    is_original = False
                    
                    # Find the version with this audio language
                    if 'versions' in episode_data:
                        for version in episode_data.get('versions', []):
                            if version.get('audio_locale') == audio_lang:
                                audio_guid = version.get('guid')
                                is_original = version.get('original', False)
                                logger.info(f"Found audio GUID for {audio_lang}: {audio_guid}")
                                if is_original:
                                    logger.info(f"This is the original audio language")
                                break
                    
                    if not audio_guid:
                        logger.warning(f"Could not find audio GUID for language {audio_lang}, skipping")
                        continue
                    
                    # Get stream info for this audio version
                    logger.info(f"Getting stream info for audio language {audio_lang}")
                    audio_stream = self.api.get_streams(audio_guid, 'en-US', cms_data, audio_guid)
                    
                    if not audio_stream or not audio_stream.get('url'):
                        logger.warning(f"Could not get stream URL for audio language {audio_lang}, skipping")
                        continue
                    
                    # Get fresh DRM information specifically for this audio stream
                    audio_keys = None
                    audio_drm_info = self.parse_mpd(audio_stream['url'], audio_stream.get('token'))
                    
                    if audio_drm_info and audio_drm_info.get("pssh") and audio_drm_info.get("license_url"):
                        logger.info(f"Getting keys specifically for audio language {audio_lang}")
                        logger.info(f"PSSH for {audio_lang}: {audio_drm_info.get('pssh')[:30]}...")
                        logger.info(f"KID for {audio_lang}: {audio_drm_info.get('kid', 'Unknown')}")
                        
                        audio_keys = self.get_license_key(
                            audio_drm_info["license_url"],
                            audio_drm_info["pssh"],
                            audio_stream.get('token'),
                            audio_stream['url'],
                            "audio"
                        )
                        
                        if audio_keys:
                            logger.info(f"Successfully retrieved {len(audio_keys)} keys for {audio_lang}")
                        else:
                            logger.warning(f"Failed to get keys for {audio_lang}, will try using video keys as fallback")
                            # Fallback to video keys if available
                            audio_keys = keys
                    else:
                        logger.warning(f"No DRM info found for {audio_lang}, using video keys as fallback if available")
                        # Fallback to video keys
                        audio_keys = keys
                    
                    # Download this audio track
                    audio_download_cmd = [
                        "N_m3u8DL-RE", 
                        audio_stream['url'],
                        "--header", f"accept-language: {audio_lang},en-US;q=0.9",
                        "--header", f"authorization: Bearer {self.api.access_token}",
                        "--header", "content-type: application/octet-stream",
                        "--header", "referer: https://static.crunchyroll.com/",
                        "--header", f"user-agent: {self.api.config.USER_AGENT}",
                        "--header", f"x-cr-content-id: {audio_guid}",
                        "--binary-merge", "false",     
                        "--save-name", f"{filename}_audio_{audio_lang}",
                        "--drop-video", ".*",      # Drop all video streams
                        "--select-audio", "best",  # Use best audio quality
                        "--drop-subtitle", ".*"    # Drop all subtitles from the stream
                    ]
                    
                    # Add audio token if available - critical for authentication
                    if audio_stream.get('token'):
                        audio_download_cmd.extend(["--header", f"x-cr-video-token: {audio_stream['token']}"])
                        logger.info(f"Added video token for {audio_lang} authentication: {audio_stream['token'][:10]}...")
                    
                    # Add audio decryption key if available
                    if audio_keys:
                        # Find a CONTENT type key for audio, or use any available key
                        content_key = None
                        key_used = None
                        
                        # First try to find a CONTENT key
                        for key in audio_keys:
                            if key.get('type') == 'CONTENT':
                                content_key = key
                                key_used = "CONTENT"
                                break
                        
                        # If no CONTENT key, try any key
                        if not content_key and audio_keys:
                            content_key = audio_keys[0]
                            key_used = "default"
                            
                        if content_key:
                            key_param = f"{content_key['key_id']}:{content_key['key']}"
                            logger.info(f"Using {key_used} key for {audio_lang} decryption")
                            logger.info(f"  Key ID: {content_key['key_id']}")
                            logger.info(f"  Key: {content_key['key']}")
                            audio_download_cmd.extend(["--key", key_param])
                    else:
                        logger.warning(f"No keys available for {audio_lang} download")
                    
                    # Run the audio download command
                    logger.info(f"Running audio download command for {audio_lang}")
                    logger.info(f"Command: {' '.join(audio_download_cmd)}")
                    
                    audio_result = subprocess.run(audio_download_cmd, cwd=cwd)
                    
                    # Clean up this audio stream
                    if audio_stream.get('token'):
                        self.api.delete_streams(audio_guid, audio_stream['token'])
                    
                    if audio_result.returncode != 0:
                        logger.error(f"Audio download failed for {audio_lang} with return code: {audio_result.returncode}")
                        # Continue to next language even if this one fails
                        continue
                    
                    logger.info(f"Audio downloaded successfully for {audio_lang}")
                    
                    # Find the downloaded audio file
                    found_audio = False
                    for file in os.listdir(season_output_dir):
                        if file.endswith('.m4a') or file.endswith('.aac'):
                            # Check if this is the file we just downloaded
                            if f"audio_{audio_lang}" in file and f"{filename}_audio_{audio_lang}" in file:
                                full_path = str(season_output_dir / file)
                                # Check if file is not empty
                                if os.path.getsize(full_path) > 0:
                                    audio_files.append(full_path)
                                    audio_languages.append(audio_lang)
                                    logger.info(f"Found valid audio file for {audio_lang}: {full_path}")
                                    
                                    # Track original audio for default selection during muxing
                                    if is_original:
                                        original_audio_index = len(audio_files) - 1
                                    found_audio = True
                                    break
                                else:
                                    logger.warning(f"Found empty audio file for {audio_lang}, skipping: {full_path}")
                    
                    if not found_audio:
                        logger.warning(f"Could not find any valid audio files for {audio_lang} after download")
                
                # If we don't have any audio files, report error but continue
                if not audio_files:
                    logger.warning("Could not find any downloaded audio files, continuing with video only")
                
                # Find the downloaded video files
                video_files = []
                
                for file in os.listdir(season_output_dir):
                    full_path = str(season_output_dir / file)
                    # Skip directories and non-files
                    if not os.path.isfile(full_path):
                        continue
                    
                    # Check if it's a video file from the download
                    if file.endswith('.m4v') or file.endswith('.mp4') or file.endswith('.h264'):
                        video_files.append(full_path)
                        logger.info(f"Found video file: {full_path}")
                
                # Sort videos by size (larger is likely better quality)
                video_files.sort(key=lambda f: os.path.getsize(f), reverse=True)
                
                # Select the first video file if available
                video_file = video_files[0] if video_files else None
                
                if not video_file:
                    logger.error("Could not find downloaded video file for muxing")
                    return False
                
                # STEP 3: PROCESS SUBTITLES
                logger.info("STEP 3: PROCESSING SUBTITLES")
                
                # Now process subtitles - get the original version's GUID first
                original_guid = None
                subtitle_files = []
                
                # Look for original version info in episode data
                if 'versions' in episode_data:
                    for version in episode_data.get('versions', []):
                        if version.get('original') is True:
                            original_guid = version.get('guid')
                            logger.info(f"Found original version with GUID: {original_guid}")
                            break
                
                # If we found an original GUID, use it to get new stream info for subtitles
                if original_guid:
                    # Get fresh CMS data for the stream request
                    index = self.api.get_index()
                    cms_data = index.get('cms', {})
                    
                    # Get stream info using the original version GUID
                    logger.info(f"Getting stream info for subtitles using original GUID: {original_guid}")
                    subtitle_streams = self.api.get_streams(original_guid, 'en-US', cms_data, original_guid)
                    
                    # Extract and download all available subtitles
                    if subtitle_streams and 'subtitles' in subtitle_streams:
                        subtitle_files = download_subtitles(subtitle_streams['subtitles'], episode_id, season_output_dir, episode_data)
                        logger.info(f"Downloaded {len(subtitle_files)} subtitle files for muxing")
                        
                        # Cleanup this stream token too
                        if subtitle_streams.get('token'):
                            self.api.delete_streams(original_guid, subtitle_streams['token'])
                else:
                    # Fall back to using subtitles from the original stream info if available
                    if 'subtitles' in stream_info:
                        subtitle_files = download_subtitles(stream_info['subtitles'], episode_id, season_output_dir, episode_data)
                        logger.info(f"Using {len(subtitle_files)} subtitles from original stream info")
                
                # Prepare for muxing with mkvtoolnix
                output_file = str(season_output_dir / f"{filename}.mkv")
                
                # For multiple audio tracks, use the original audio as default if available
                # If not, use the first audio file
                default_audio_lang = None
                
                if original_audio_index >= 0 and original_audio_index < len(audio_languages):
                    default_audio_lang = audio_languages[original_audio_index]
                    logger.info(f"Using original audio {default_audio_lang} as default track")
                elif audio_languages:
                    default_audio_lang = audio_languages[0]
                    logger.info(f"Using first audio {default_audio_lang} as default track")
                
                # Mux files together (with multiple audio tracks)
                mux_success = mux_media_files(
                    video_file, 
                    audio_files,  # Now a list of audio files
                    subtitle_files, 
                    chapter_file, 
                    output_file,
                    default_audio_lang,
                    audio_languages  # Pass language codes for proper track naming
                )
                
                if mux_success:
                    # Clean up temporary files
                    files_to_delete = []
                    
                    # Add video and audio files to cleanup list
                    if os.path.exists(output_file):
                        if video_file:
                            files_to_delete.append(video_file)
                        
                        # Add all audio files
                        for audio_file in audio_files:
                            if audio_file and os.path.exists(audio_file):
                                files_to_delete.append(audio_file)
                        
                        # Add subtitle files
                        for sub_file in subtitle_files:
                            if os.path.exists(sub_file):
                                files_to_delete.append(sub_file)
                        
                        # Add chapter file
                        if chapter_file and os.path.exists(chapter_file):
                            files_to_delete.append(chapter_file)
                            
                        # Clean up all temporary files
                        clean_temp_files(files_to_delete)
                        
                        # Remove subtitles directory
                        subtitles_dir = str(season_output_dir / "subtitles")
                        if os.path.exists(subtitles_dir):
                            clean_temp_files([], [subtitles_dir])
                else:
                    logger.warning("Muxing failed, keeping original files")
                
                return True
                
            except Exception as e:
                logger.error(f"Error during download: {str(e)}", exc_info=True)
                # If no keys were provided and download failed, inform the user
                if not keys:
                    logger.error("Download failed without decryption keys. This content might be DRM protected.")
                    logger.info("You need a proper Widevine CDM to decrypt this content.")
                return False
                
        except Exception as e:
            logger.error(f"Error in download_episode: {str(e)}", exc_info=True)
            return False 