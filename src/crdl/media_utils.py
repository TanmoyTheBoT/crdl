"""Media utilities for Crunchyroll downloader"""
import logging
import os
import re
import requests
from pathlib import Path
from typing import Dict, List, Optional, Union
import xml.etree.ElementTree as ET
import subprocess

from .config import sanitize_filename, save_json

logger = logging.getLogger("CrunchyrollDownloader")

# Default configuration values
DEFAULT_CONFIG = {
    'release_group': 'TANMOY',
    'default_quality': '1080p',
    'default_audio': 'ja-JP'
}

def get_episode_number(episode_data: Dict) -> Union[str, float, int, None]:
    """
    Extract the episode number from episode data using a consistent approach.
    Always prioritizes sequence_number when available.
    
    Args:
        episode_data: Episode data from API
        
    Returns:
        Union[str, float, int, None]: The episode number, or None if not found
    """
    # Check all three possible fields
    numerical_episode = episode_data.get('episode_number')
    special_episode = episode_data.get('episode')
    sequence_num = episode_data.get('sequence_number')
    
    # Decision logic for which episode number to use - ALWAYS prioritize sequence_number
    if sequence_num is not None:
        # Use sequence number as primary source
        return sequence_num
    elif numerical_episode is not None:
        # Use numerical episode if sequence_number not available
        return numerical_episode
    elif special_episode is not None and isinstance(special_episode, str) and special_episode.startswith("SP"):
        # Use special episode marker if it's a special episode
        return special_episode
    else:
        # Try to extract episode number from the title
        title = episode_data.get('title', '')
        ep_match = re.search(r'Episode\s+(\d+)', title, re.IGNORECASE)
        if ep_match:
            return ep_match.group(1)
    
    # If all else fails, return None
    return None

def format_episode_number(episode_number) -> str:
    """
    Format episode number consistently for filenames
    
    Args:
        episode_number: The episode number value to format
        
    Returns:
        str: Formatted episode number
    """
    if episode_number is None:
        return "01"  # Default
    
    # Handle special episode markers
    if isinstance(episode_number, str) and episode_number.startswith("SP"):
        return episode_number
    
    # Format numerical episode with leading zeros
    return str(episode_number).zfill(2)

def extract_metadata(episode_data: Dict) -> Dict[str, str]:
    """
    Extract episode metadata for filename construction
    
    Args:
        episode_data: Episode data from API
        
    Returns:
        Dict: Dictionary with series_title, episode_number, episode_title, etc.
    """
    # Initialize result
    metadata = {
        'series_title': 'Crunchyroll_Anime',
        'episode_number': '01',
        'episode_title': 'Episode',
        'season_number': '01',
        'quality': '1080p',
        'audio_locale': 'ja-JP'  # Default to Japanese audio
    }
    
    # Get series title
    series_title = None
    if 'series_title' in episode_data:
        series_title = episode_data.get('series_title')
    elif 'series_name' in episode_data:
        series_title = episode_data.get('series_name')
    elif 'title' in episode_data.get('series', {}):
        series_title = episode_data.get('series', {}).get('title')
    else:
        # Look for other possible paths to the series title
        for path in ['collection.title', 'season.title', 'parent.title']:
            parts = path.split('.')
            data = episode_data
            found = True
            for part in parts:
                if part in data:
                    data = data[part]
                else:
                    found = False
                    break
            if found and isinstance(data, str):
                series_title = data
                break
    
    if series_title:
        metadata['series_title'] = sanitize_filename(series_title)
    
    # Get episode number using the common helper function
    episode_number = get_episode_number(episode_data)
    metadata['episode_number'] = format_episode_number(episode_number)
    
    # Get episode title
    episode_title = episode_data.get('title', 'Episode')
    metadata['episode_title'] = sanitize_filename(episode_title)
    
    # Get season number
    season_number = None
    if 'season_number' in episode_data:
        season_number = episode_data.get('season_number')
    elif 'season' in episode_data and 'number' in episode_data.get('season', {}):
        season_number = episode_data.get('season', {}).get('number')
    elif 'collection' in episode_data and 'number' in episode_data.get('collection', {}):
        season_number = episode_data.get('collection', {}).get('number')
    
    if season_number:
        metadata['season_number'] = str(season_number).zfill(2)
    
    # Get audio locale
    if 'audio_locale' in episode_data:
        metadata['audio_locale'] = episode_data.get('audio_locale')
    
    return metadata

def format_filename_part(text: str) -> str:
    """
    Format a part of a filename to be safe and consistent
    
    Args:
        text: The text to format
        
    Returns:
        str: Formatted text suitable for use in filenames
    """
    if not text:
        return ""
        
    # Replace special characters directly
    text = text.replace(',', '.')
    text = text.replace('-', '.')
    text = text.replace('?', '')
    text = text.replace('!', '')
    text = text.replace('\'', '')
    text = text.replace('"', '')
    
    # Fix typical problems like "E-Rank..Are.You-"
    text = re.sub(r'\.+', '.', text)  # Replace multiple dots with a single dot
    text = text.strip('.-')  # Remove dots or dashes at start/end
    
    return text

def construct_filename(metadata: Dict[str, str], config: Dict = None) -> str:
    """
    Construct a standardized filename for the episode using metadata and config
    
    Args:
        metadata: Dictionary with episode metadata
        config: Optional configuration dictionary to override defaults
        
    Returns:
        str: Formatted filename
    """
    # Use default config if none provided, or merge with provided config
    cfg = DEFAULT_CONFIG.copy()
    if config:
        cfg.update(config)
    
    release_group = cfg.get('release_group', 'TANMOY')
    quality = metadata.get('quality', cfg.get('default_quality', '1080p'))
    
    # Construct filename in standard anime naming format
    filename = f"{metadata['series_title']}.S{metadata['season_number']}E{metadata['episode_number']}"
    
    # Add episode title if available and not generic
    if metadata['episode_title'] and metadata['episode_title'].lower() != 'episode':
        # Format episode title
        episode_title = format_filename_part(metadata['episode_title'])
        if episode_title:
            filename += f".{episode_title}"
        
    # Add quality and format info
    filename += f".{quality}.CR.WEB-DL.AAC2.0.H.264-{release_group}"
    
    # Final cleanup
    filename = sanitize_filename(filename)
    filename = re.sub(r'\.+', '.', filename)  # Replace multiple dots with a single dot
    filename = filename.strip('.-')  # Ensure no trailing dots or dashes
    
    return filename

def clean_subtitle_file(filepath: str) -> bool:
    """
    Remove empty dialogue lines from subtitle files
    
    Args:
        filepath: Path to the subtitle file
        
    Returns:
        bool: True if cleaning was successful, False otherwise
    """
    try:
        # Open and read the subtitle file
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        
        # Pattern for empty dialogue lines
        empty_dialogue_pattern = re.compile(r'^Dialogue:\s+\d+,\d+:\d+:\d+\.\d+,\d+:\d+:\d+\.\d+,.*?,,\d+,\d+,\d+,,\s*$')
        
        # Filter out empty dialogue lines
        cleaned_lines = [line for line in lines if not empty_dialogue_pattern.match(line)]
        
        # Write the cleaned content back to the file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(cleaned_lines)
            
        # Calculate how many lines were removed
        removed_count = len(lines) - len(cleaned_lines)
        if removed_count > 0:
            logger.info(f"Removed {removed_count} empty dialogue lines from {filepath}")
            
        return True
        
    except Exception as e:
        logger.error(f"Error cleaning subtitle file {filepath}: {str(e)}")
        return False

def download_subtitles(subtitles_data: Dict, episode_id: str, output_dir: Path, episode_data: Dict = None) -> List[str]:
    """
    Download subtitles from streams response
    
    Args:
        subtitles_data: Dictionary containing subtitle information
        episode_id: ID of the episode
        output_dir: Directory to save the subtitles (season directory)
        episode_data: Optional episode metadata for better filename construction
        
    Returns:
        List[str]: List of paths to downloaded subtitle files
    """
    if not subtitles_data:
        logger.warning("No subtitles found in streams response")
        return []
    
    # Create subtitles directory within the season folder if it doesn't exist
    subtitles_dir = output_dir / "subtitles"
    subtitles_dir.mkdir(exist_ok=True)
    
    logger.info(f"Downloading subtitles for episode {episode_id}")
    
    subtitle_files = []
    for lang, subtitle_info in subtitles_data.items():
        try:
            url = subtitle_info.get('url')
            if not url:
                logger.warning(f"No URL found for {lang} subtitle")
                continue
                
            # Get subtitle format
            subtitle_format = subtitle_info.get('format', 'ass')
            
            # Construct filename
            if episode_data:
                # Use proper naming if we have episode data
                metadata = extract_metadata(episode_data)
                base_filename = f"{metadata['series_title']}.S{metadata['season_number']}E{metadata['episode_number']}"
                filename = f"{base_filename}.{lang}.{subtitle_format}"
            else:
                # Fallback to episode_id based naming
                filename = f"{episode_id}.{lang}.{subtitle_format}"
                
            filepath = subtitles_dir / filename
            
            # Download subtitle file
            logger.info(f"Downloading {lang} subtitle from {url}")
            
            headers = {
                'User-Agent': 'Crunchyroll/3.78.3 Android/15 okhttp/4.12.0',
                'Accept-Language': f'{lang},en-US;q=0.9',
                'Referer': 'https://static.crunchyroll.com/',
                'Origin': 'https://static.crunchyroll.com/'
            }
            
            response = requests.get(url, headers=headers)
            
            if response.status_code != 200:
                logger.error(f"Failed to download {lang} subtitle: {response.status_code}")
                continue
            
            # Save subtitle file
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            logger.info(f"Saved {lang} subtitle to {filepath}")
            
            # Clean subtitle file to remove empty dialogue lines
            if subtitle_format.lower() in ['ass', 'ssa']:
                clean_subtitle_file(str(filepath))
            
            subtitle_files.append(str(filepath))
            
        except Exception as e:
            logger.error(f"Error downloading {lang} subtitle: {str(e)}")
            continue
    
    logger.info(f"Downloaded {len(subtitle_files)} subtitle files")
    return subtitle_files

def extract_chapter_info(episode_data: Dict, episode_id: str, output_dir: Path) -> Optional[str]:
    """
    Extract chapter information from episode data and create chapter file for mkvmerge
    
    Args:
        episode_data: Episode data from API
        episode_id: ID of the episode
        output_dir: Directory to save the chapter file (season directory)
        
    Returns:
        Optional[str]: Path to the chapter file, or None if no chapters found
    """
    try:
        # Get metadata for filename consistency
        metadata = extract_metadata(episode_data)
        episode_prefix = f"{metadata['series_title']}_S{metadata['season_number']}E{metadata['episode_number']}"
        
        # Check if episode data has chapter information
        chapters = []
        
        # Look for chapter markers in episode data - these are the most accurate
        if 'playback_position_markers' in episode_data:
            markers = episode_data.get('playback_position_markers', [])
            for marker in markers:
                if marker.get('type') == 'chapter' and 'time' in marker:
                    title = marker.get('title', f"Chapter")
                    chapters.append({
                        'time': marker['time'],
                        'title': title
                    })
                    
        # Try to find chapters in the episode's timeline data if available
        if 'timeline' in episode_data:
            timeline = episode_data.get('timeline', [])
            for item in timeline:
                if 'time' in item:
                    title = item.get('title', f"Chapter")
                    chapters.append({
                        'time': item['time'],
                        'title': title
                    })
        
        # Check for Crunchyroll's segment data which often contains accurate chapter info
        if 'segments' in episode_data:
            segments = episode_data.get('segments', [])
            for segment in enumerate(segments):
                if 'start_time' in segment:
                    title = segment.get('title', 'Chapter')
                    chapters.append({
                        'time': segment['start_time'],
                        'title': title
                    })
        
        # Also check for official chapters in the HLS playlist or MPD
        # These are often embedded in the stream metadata
        
        if not chapters:
            logger.info("No official chapter information found in episode data")
            return None
            
        # Sort chapters by time and ensure they're unique
        chapters.sort(key=lambda x: float(x['time']))
        
        # Create chapter file in XML format for mkvmerge with consistent naming
        chapter_file = output_dir / f"{metadata['series_title']}.S{metadata['season_number']}E{metadata['episode_number']}.chapters.xml"
        
        with open(chapter_file, 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0"?>\n')
            f.write('<!-- <!DOCTYPE Chapters SYSTEM "matroskachapters.dtd"> -->\n')
            f.write('<Chapters>\n')
            f.write('  <EditionEntry>\n')
            
            for i, chapter in enumerate(chapters):
                # Convert time to format HH:MM:SS.nnn
                time_sec = float(chapter['time'])
                hours = int(time_sec / 3600)
                minutes = int((time_sec % 3600) / 60)
                seconds = time_sec % 60
                time_str = f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"
                
                # Get title or use index if not available
                title = chapter.get('title', f"Chapter {i+1}")
                
                # Sanitize title for XML
                title = title.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                
                f.write('    <ChapterAtom>\n')
                f.write(f'      <ChapterUID>{i+1}</ChapterUID>\n')
                f.write(f'      <ChapterTimeStart>{time_str}</ChapterTimeStart>\n')
                f.write(f'      <ChapterDisplay>\n')
                f.write(f'        <ChapterString>{title}</ChapterString>\n')
                f.write(f'        <ChapterLanguage>eng</ChapterLanguage>\n')
                f.write(f'      </ChapterDisplay>\n')
                f.write('    </ChapterAtom>\n')
            
            f.write('  </EditionEntry>\n')
            f.write('</Chapters>\n')
        
        # Log all chapter info for verification
        logger.info(f"Created chapter file with {len(chapters)} official chapters:")
        for i, chapter in enumerate(chapters):
            time_sec = float(chapter['time'])
            hours = int(time_sec / 3600)
            minutes = int((time_sec % 3600) / 60)
            seconds = time_sec % 60
            time_fmt = f"{hours:02d}:{minutes:02d}:{seconds:02.0f}"
            logger.info(f"  Chapter {i+1}: {time_fmt} - {chapter['title']}")
        
        return str(chapter_file)
        
    except Exception as e:
        logger.error(f"Error extracting chapter information: {str(e)}", exc_info=True)
        return None

def clean_temp_files(files_to_remove: List[str], dirs_to_remove: List[str] = None) -> None:
    """
    Clean up temporary files after successful muxing
    
    Args:
        files_to_remove: List of file paths to remove
        dirs_to_remove: Optional list of directory paths to remove including contents
    """
    # Remove individual files
    for file_path in files_to_remove:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Deleted temporary file: {file_path}")
        except Exception as e:
            logger.error(f"Failed to delete file {file_path}: {str(e)}")
    
    # Remove directories if specified
    if dirs_to_remove:
        for dir_path in dirs_to_remove:
            try:
                if os.path.exists(dir_path) and os.path.isdir(dir_path):
                    # Remove all files in directory first
                    for root, dirs, files in os.walk(dir_path, topdown=False):
                        for file in files:
                            try:
                                file_path = os.path.join(root, file)
                                os.remove(file_path)
                                logger.debug(f"Deleted file in directory: {file_path}")
                            except Exception as e:
                                logger.error(f"Failed to delete file in directory {file_path}: {str(e)}")
                        
                        # Then remove empty subdirectories
                        for dir_name in dirs:
                            try:
                                subdir_path = os.path.join(root, dir_name)
                                os.rmdir(subdir_path)
                                logger.debug(f"Deleted subdirectory: {subdir_path}")
                            except Exception as e:
                                logger.error(f"Failed to delete subdirectory {subdir_path}: {str(e)}")
                    
                    # Finally remove the main directory
                    os.rmdir(dir_path)
                    logger.info(f"Deleted directory with all contents: {dir_path}")
            except Exception as e:
                logger.error(f"Failed to delete directory {dir_path}: {str(e)}")

def mux_media_files(video_file: str, audio_file: Union[str, List[str]], subtitle_files: List[str], 
                   chapter_file: str, output_file: str, audio_language: str = None, 
                   audio_languages: List[str] = None) -> bool:
    """
    Mux video, audio, subtitles and chapters into a MKV file
    
    Args:
        video_file: Path to the video file
        audio_file: Path to the audio file or list of audio files
        subtitle_files: List of paths to subtitle files
        chapter_file: Path to the chapter file (or None if not available)
        output_file: Path to the output MKV file
        audio_language: ISO language code for the default audio track
        audio_languages: List of ISO language codes for each audio track (only used when audio_file is a list)
        
    Returns:
        bool: True if muxing was successful, False otherwise
    """
    try:
        # Verify that input files exist
        if not os.path.exists(video_file):
            logger.error(f"Video file does not exist: {video_file}")
            return False
        
        # Handle both single audio file and list of audio files
        audio_files = []
        
        if isinstance(audio_file, list):
            # Multiple audio files
            for af in audio_file:
                if af and os.path.exists(af):
                    audio_files.append(af)
                else:
                    if af:
                        logger.warning(f"Audio file does not exist: {af}")
        elif audio_file:
            # Single audio file
            if os.path.exists(audio_file):
                audio_files.append(audio_file)
            else:
                logger.warning(f"Audio file does not exist: {audio_file}")
        
        # Filter subtitle files that actually exist
        existing_subtitle_files = []
        for sub_file in subtitle_files:
            if os.path.exists(sub_file):
                existing_subtitle_files.append(sub_file)
            else:
                logger.warning(f"Subtitle file does not exist: {sub_file}")
                
        # If chapter file doesn't exist, set to None
        if chapter_file and not os.path.exists(chapter_file):
            logger.warning(f"Chapter file does not exist: {chapter_file}")
            chapter_file = None
        
        # Construct the command with absolute paths
        output_file_abs = os.path.abspath(output_file)
        video_file_abs = os.path.abspath(video_file)
        
        # Start building command
        mkvmerge_args = [
            "mkvmerge", 
            "-o", output_file_abs, 
            video_file_abs
        ]
        
        # Add audio files if available
        for i, af in enumerate(audio_files):
            audio_file_abs = os.path.abspath(af)
            
            # Determine language for this audio track
            track_lang = "und"  # Default undefined
            is_default = False
            
            # If we have a list of audio languages, use the corresponding one
            if audio_languages and i < len(audio_languages):
                track_lang = audio_languages[i]
                
                # Check if this is the default audio track
                if audio_language and audio_language == track_lang:
                    is_default = True
                
            # If this is the first track and no specific default is set, make it default
            elif i == 0 and not audio_language:
                is_default = True
            
            # Add language and default flags
            mkvmerge_args.extend([
                "--language", f"0:{track_lang}",
                "--track-name", f"0:{track_lang}",
                "--audio-tracks", "0"     # Use only first audio track from file
            ])
            
            # Set default flag if this is the default track
            if is_default:
                mkvmerge_args.extend(["--default-track", "0:yes"])
                logger.info(f"Setting audio track {track_lang} as default")
            else:
                mkvmerge_args.extend(["--default-track", "0:no"])
            
            logger.info(f"Adding audio track {i+1} with language: {track_lang}")
            mkvmerge_args.append(audio_file_abs)
        
        # Add subtitles
        for sub_file in existing_subtitle_files:
            sub_file_abs = os.path.abspath(sub_file)
            
            # Extract language code from filename exactly as is
            try:
                # Get the raw language code from the filename
                sub_lang = os.path.basename(sub_file).split('.')[-2]
            except Exception:
                logger.warning(f"Could not extract language code from {sub_file}, using 'und'")
                sub_lang = 'und'  # Undefined language as fallback
            
            # Use the raw language code without modification
            mkvmerge_args.extend([
                "--language", f"0:{sub_lang}", 
                "--track-name", f"0:{sub_lang}",
                "--default-track", "0:no",     # Explicitly set subtitle to not be default
                "--forced-track", "0:no",      # Explicitly set subtitle to not be forced
                "--compression", "0:none",     # No compression for subtitles
                sub_file_abs
            ])
        
        # Add chapter file if available
        if chapter_file:
            chapter_file_abs = os.path.abspath(chapter_file)
            mkvmerge_args.extend(["--chapters", chapter_file_abs])
        
        # Build track order to ensure default audio is first
        track_orders = []
        
        # First add video track (always 0:0 from first file)
        track_orders.append("0:0")
        
        # Add audio tracks in correct order
        for i in range(len(audio_files)):
            # Audio file index + track 0 (we only take first track from each audio file)
            track_orders.append(f"{i+1}:0")
            
        # Add subtitle tracks
        for i in range(len(existing_subtitle_files)):
            # Subtitle files start after video + audio files, and we only take track 0
            track_orders.append(f"{len(audio_files)+i+1}:0")
        
        # Add track order parameter at the end
        if track_orders:
            mkvmerge_args.extend(["--track-order", ",".join(track_orders)])
        
        logger.info(f"Running mkvmerge command: {' '.join(mkvmerge_args)}")
        
        # Execute the command
        result = subprocess.run(mkvmerge_args, check=False)
        
        # Check the result
        if result.returncode == 0 or result.returncode == 1:
            # mkvmerge returns 1 for warnings, which is still a success
            logger.info(f"Successfully muxed files into {output_file}")
            
            return True
        else:
            logger.error(f"Failed to mux files, mkvmerge returned: {result.returncode}")
            return False
            
    except Exception as e:
        logger.error(f"Error running mkvmerge: {str(e)}", exc_info=True)
        return False

def construct_series_folder_name(series_title: str, season_number: str = "01", quality: str = "1080p", series_data: Dict = None, config: Dict = None) -> str:
    """
    Construct a standardized folder name for the main series directory
    
    Args:
        series_title: Title of the series
        season_number: Current season number (not used in main folder name)
        quality: Video quality (e.g., '1080p')
        series_data: Optional series data (not used in main folder name)
        config: Optional configuration dictionary
        
    Returns:
        str: Formatted folder name
    """
    # Use default config if none provided, or merge with provided config
    cfg = DEFAULT_CONFIG.copy()
    if config:
        cfg.update(config)
    
    # Get release group from config
    release_group = cfg.get('release_group', 'TANMOY')
    
    # Create the folder name without any season information
    folder_name = f"{series_title}.{quality}.CR.WEB-DL.AAC2.0.H.264-{release_group}"
    
    # Clean the folder name by removing invalid characters
    folder_name = sanitize_filename(folder_name)
    folder_name = re.sub(r'\.+', '.', folder_name)  # Replace multiple dots with a single dot
    folder_name = folder_name.strip('.-')  # Ensure no trailing dots or dashes
    
    return folder_name

def construct_season_folder_name(series_title: str, season_number: str, quality: str = "1080p", config: Dict = None) -> str:
    """
    Construct a standardized folder name for season directory
    
    Args:
        series_title: Title of the series
        season_number: Season number
        quality: Video quality (e.g., '1080p')
        config: Optional configuration dictionary
        
    Returns:
        str: Formatted folder name
    """
    # Use default config if none provided, or merge with provided config
    cfg = DEFAULT_CONFIG.copy()
    if config:
        cfg.update(config)
    
    # Get release group from config
    release_group = cfg.get('release_group', 'TANMOY')
    
    # Create folder name
    folder_name = f"{series_title}.S{season_number}.{quality}.CR.WEB-DL.AAC2.0.H.264-{release_group}"
    
    # Final cleanup
    folder_name = sanitize_filename(folder_name)
    folder_name = re.sub(r'\.+', '.', folder_name)
    folder_name = folder_name.strip('.-')
    
    return folder_name 