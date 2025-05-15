"""Crunchyroll API client module"""
import requests
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4
import time

from .config import CrunchyrollConfig, save_json

logger = logging.getLogger("CrunchyrollDownloader")

class CrunchyrollAPI:
    """Handles interactions with the Crunchyroll API"""
    
    def __init__(self, username: str, password: str, config=None, config_dirs=None):
        """
        Initialize the Crunchyroll API client
        
        Args:
            username: Crunchyroll username
            password: Crunchyroll password
            config: Optional custom configuration
            config_dirs: Optional custom directory paths
        """
        self.username = username
        self.password = password
        self.access_token = None
        self.refresh_token = None
        self.token_expiry = None
        self.cookies = None
        self.profile = None
        self.account_id = None
        self.external_id = None
        self.config = config or CrunchyrollConfig(config_dirs)
        self.last_token_refresh = 0
        
        # Use json_dir from config
        self.json_dir = self.config.json_dir
    
    def login(self) -> bool:
        """
        Login to Crunchyroll and get access token
        
        Returns:
            bool: True if login was successful, False otherwise
        """
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': self.config.AUTHORIZATION,
            'User-Agent': self.config.USER_AGENT
        }
        
        data = {
            'grant_type': 'password',
            'username': self.username,
            'password': self.password,
            'scope': 'offline_access',
            'device_id': self.config.DEVICE_ID,
            'device_type': self.config.DEVICE_TYPE,
            'device_name': self.config.DEVICE_NAME
        }
        
        try:
            response = requests.post(self.config.AUTH_URL, headers=headers, data=data)
            response.raise_for_status()
            
            resp_data = response.json()
            self.access_token = resp_data['access_token']
            self.refresh_token = resp_data['refresh_token']
            self.token_expiry = time.time() + resp_data.get('expires_in', 3600)
            self.cookies = response.cookies
            self.last_token_refresh = time.time()
            
            # Save login info to file
            save_json(resp_data, 'login.json', self.json_dir)
            
            logger.info("Login successful")
            return True
            
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            if 'response' in locals() and response:
                logger.error(f"Response: {response.status_code} {response.text}")
            return False
    
    def refresh_access_token(self) -> bool:
        """
        Refresh the access token using the refresh token
        
        Returns:
            bool: True if refresh was successful, False otherwise
        """
        # Don't attempt refreshes too frequently (at least 5 seconds between attempts)
        if time.time() - self.last_token_refresh < 5:
            logger.warning("Token refresh attempted too soon after previous refresh")
            return False
            
        if not self.refresh_token:
            logger.error("No refresh token available. Need to login again.")
            return self.login()
            
        logger.info("Refreshing access token")
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': self.config.AUTHORIZATION,
            'User-Agent': self.config.USER_AGENT
        }
        
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token,
            'scope': 'offline_access',
            'device_id': self.config.DEVICE_ID,
            'device_type': self.config.DEVICE_TYPE,
            'device_name': self.config.DEVICE_NAME
        }
        
        try:
            response = requests.post(self.config.AUTH_URL, headers=headers, data=data)
            response.raise_for_status()
            
            resp_data = response.json()
            self.access_token = resp_data['access_token']
            self.refresh_token = resp_data['refresh_token']
            self.token_expiry = time.time() + resp_data.get('expires_in', 3600) 
            self.cookies = response.cookies
            self.last_token_refresh = time.time()
            
            # Save refreshed login info to file
            save_json(resp_data, 'login_refreshed.json', self.json_dir)
            
            logger.info("Access token refreshed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Token refresh failed: {str(e)}")
            if 'response' in locals() and response:
                logger.error(f"Response: {response.status_code} {response.text}")
            # If refresh fails, attempt full login
            logger.info("Attempting full login after refresh failure")
            return self.login()
    
    def check_token_valid(self) -> bool:
        """
        Check if the current token is valid or needs refreshing
        
        Returns:
            bool: True if token is valid, False otherwise
        """
        # If we don't have a token or it's expired (with 60-second buffer)
        if not self.access_token or (self.token_expiry and time.time() > self.token_expiry - 60):
            logger.info("Access token expired or missing, refreshing")
            if self.refresh_token:
                return self.refresh_access_token()
            else:
                return self.login()
        return True
    
    def get_profile(self) -> Dict:
        """
        Get user profile information
        
        Returns:
            Dict: Profile information
        """
        if not self.access_token:
            raise ValueError("Not logged in. Call login() first.")
            
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'User-Agent': self.config.USER_AGENT
        }
        
        try:
            response = requests.get(self.config.PROFILE_URL, headers=headers, cookies=self.cookies)
            response.raise_for_status()
            
            profile_data = response.json()
            self.profile = profile_data
            save_json(profile_data, 'profile.json', self.json_dir)
            
            logger.info(f"Profile retrieved successfully for: {profile_data.get('username', profile_data.get('email', 'Unknown'))}")
            return profile_data
            
        except Exception as e:
            logger.error(f"Failed to get profile: {str(e)}")
            if response:
                logger.error(f"Response: {response.status_code} {response.text}")
            raise
    
    def get_accounts(self) -> Dict:
        """
        Get account information
        
        Returns:
            Dict: Account information
        """
        if not self.access_token:
            raise ValueError("Not logged in. Call login() first.")
            
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'User-Agent': self.config.USER_AGENT
        }
        
        try:
            response = requests.get(self.config.ACCOUNTS_URL, headers=headers, cookies=self.cookies)
            response.raise_for_status()
            
            accounts_data = response.json()
            save_json(accounts_data, 'accounts.json', self.json_dir)
            
            # Store account and external IDs
            self.external_id = accounts_data.get('external_id')
            self.account_id = accounts_data.get('account_id')
            
            logger.info(f"Accounts retrieved successfully. External ID: {self.external_id}, Account ID: {self.account_id}")
            return accounts_data
            
        except Exception as e:
            logger.error(f"Failed to get accounts: {str(e)}")
            if response:
                logger.error(f"Response: {response.status_code} {response.text}")
            raise
    
    def get_subscription(self) -> Dict:
        """
        Get subscription information
        
        Returns:
            Dict: Subscription information
        """
        if not self.access_token or not self.external_id:
            raise ValueError("Not logged in or missing external ID. Call login() and get_accounts() first.")
            
        subscription_url = f'https://beta-api.crunchyroll.com/subs/v1/subscriptions/{self.external_id}/benefits'
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'User-Agent': self.config.USER_AGENT
        }
        
        try:
            response = requests.get(subscription_url, headers=headers, cookies=self.cookies)
            response.raise_for_status()
            
            subscription_data = response.json()
            save_json(subscription_data, 'subscription.json', self.json_dir)
            
            logger.info("Subscription retrieved successfully")
            return subscription_data
            
        except Exception as e:
            logger.error(f"Failed to get subscription: {str(e)}")
            if response:
                logger.error(f"Response: {response.status_code} {response.text}")
            return {}  # Return empty dict instead of raising to allow continuing
    
    def get_index(self) -> Dict:
        """
        Get CMS index information
        
        Returns:
            Dict: CMS index information containing bucket, policy, signature, etc.
        """
        if not self.access_token:
            raise ValueError("Not logged in. Call login() first.")
            
        index_url = 'https://beta-api.crunchyroll.com/index/v2'
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'User-Agent': self.config.USER_AGENT
        }
        
        try:
            response = requests.get(index_url, headers=headers, cookies=self.cookies)
            response.raise_for_status()
            
            index_data = response.json()
            save_json(index_data, 'index.json', self.json_dir)
            
            logger.info("CMS index retrieved successfully")
            return index_data
            
        except Exception as e:
            logger.error(f"Failed to get index: {str(e)}")
            if response:
                logger.error(f"Response: {response.status_code} {response.text}")
            raise

    def get_series(self, series_id: str, locale: str, cms_data: Dict) -> Dict:
        """
        Get series information
        
        Args:
            series_id: ID of the series
            locale: Content locale (e.g., 'en-US')
            cms_data: CMS data containing bucket, policy, signature, and key_pair_id
            
        Returns:
            Dict: Series information
        """
        bucket = cms_data.get('bucket', '')
        policy = cms_data.get('policy', '')
        signature = cms_data.get('signature', '')
        key_pair_id = cms_data.get('key_pair_id', '')
        
        series_url = f'https://beta-api.crunchyroll.com/cms/v2{bucket}/series/{series_id}'
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'User-Agent': self.config.USER_AGENT
        }

        params = {
            'Policy': policy,
            'Signature': signature,
            'Key-Pair-Id': key_pair_id,
            'locale': locale
        }

        try:
            response = requests.get(series_url, headers=headers, cookies=self.cookies, params=params)
            response.raise_for_status()
            
            series_data = response.json()
            save_json(series_data, 'series.json', self.json_dir)
            
            logger.info(f"Series retrieved successfully: {series_data.get('title', 'Unknown')}")
            return series_data
            
        except Exception as e:
            logger.error(f"Failed to get series: {str(e)}")
            if response:
                logger.error(f"Response: {response.status_code} {response.text}")
            raise
    
    def get_seasons(self, series_id: str, locale: str, cms_data: Dict) -> Dict:
        """
        Get seasons for a series
        
        Args:
            series_id: ID of the series
            locale: Content locale (e.g., 'en-US')
            cms_data: CMS data containing bucket, policy, signature, and key_pair_id
            
        Returns:
            Dict: Seasons information
        """
        bucket = cms_data.get('bucket', '')
        policy = cms_data.get('policy', '')
        signature = cms_data.get('signature', '')
        key_pair_id = cms_data.get('key_pair_id', '')
        
        seasons_url = f'https://beta-api.crunchyroll.com/cms/v2{bucket}/seasons'
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'User-Agent': self.config.USER_AGENT
        }

        params = {
            'Policy': policy,
            'Signature': signature,
            'Key-Pair-Id': key_pair_id,
            'locale': locale,
            'series_id': series_id
        }

        try:
            response = requests.get(seasons_url, headers=headers, cookies=self.cookies, params=params)
            response.raise_for_status()
            
            seasons_data = response.json()
            save_json(seasons_data, 'seasons.json', self.json_dir)
            
            season_count = len(seasons_data.get('items', []))
            logger.info(f"Retrieved {season_count} seasons successfully")
            return seasons_data
            
        except Exception as e:
            logger.error(f"Failed to get seasons: {str(e)}")
            if response:
                logger.error(f"Response: {response.status_code} {response.text}")
            raise
    
    def get_episodes(self, season_id: str, locale: str, cms_data: Dict) -> Dict:
        """
        Get episodes for a season
        
        Args:
            season_id: ID of the season
            locale: Content locale (e.g., 'en-US')
            cms_data: CMS data containing bucket, policy, signature, and key_pair_id
            
        Returns:
            Dict: Episodes information
        """
        bucket = cms_data.get('bucket', '')
        policy = cms_data.get('policy', '')
        signature = cms_data.get('signature', '')
        key_pair_id = cms_data.get('key_pair_id', '')
        
        episodes_url = f'https://beta-api.crunchyroll.com/cms/v2{bucket}/episodes'
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'User-Agent': self.config.USER_AGENT
        }

        params = {
            'Policy': policy,
            'Signature': signature,
            'Key-Pair-Id': key_pair_id,
            'locale': locale,
            'season_id': season_id
        }

        try:
            response = requests.get(episodes_url, headers=headers, cookies=self.cookies, params=params)
            response.raise_for_status()
            
            episodes_data = response.json()
            save_json(episodes_data, 'episodes.json', self.json_dir)
            
            episode_count = len(episodes_data.get('items', []))
            logger.info(f"Retrieved {episode_count} episodes successfully")
            return episodes_data
            
        except Exception as e:
            logger.error(f"Failed to get episodes: {str(e)}")
            if response:
                logger.error(f"Response: {response.status_code} {response.text}")
            raise
    
    def get_episode(self, episode_id: str, locale: str, cms_data: Dict) -> Dict:
        """
        Get information for a specific episode
        
        Args:
            episode_id: ID of the episode
            locale: Content locale (e.g., 'en-US')
            cms_data: CMS data containing bucket, policy, signature, and key_pair_id
            
        Returns:
            Dict: Episode information
        """
        bucket = cms_data.get('bucket', '')
        policy = cms_data.get('policy', '')
        signature = cms_data.get('signature', '')
        key_pair_id = cms_data.get('key_pair_id', '')
        
        episode_url = f'https://beta-api.crunchyroll.com/cms/v2{bucket}/episodes/{episode_id}'
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'User-Agent': self.config.USER_AGENT
        }

        params = {
            'Policy': policy,
            'Signature': signature,
            'Key-Pair-Id': key_pair_id,
            'locale': locale
        }

        try:
            response = requests.get(episode_url, headers=headers, cookies=self.cookies, params=params)
            response.raise_for_status()
            
            episode_data = response.json()
            save_json(episode_data, 'episode.json', self.json_dir)
            
            logger.info(f"Episode retrieved successfully: {episode_data.get('title', 'Unknown')}")
            return episode_data
            
        except Exception as e:
            logger.error(f"Failed to get episode: {str(e)}")
            if response:
                logger.error(f"Response: {response.status_code} {response.text}")
            raise
    
    def get_streams(self, episode_id: str, locale: str, cms_data: Dict, guid: str) -> Dict:
        """
        Get stream information for an episode
        
        Args:
            episode_id: ID of the episode
            locale: Content locale (e.g., 'en-US')
            cms_data: CMS data containing bucket, policy, signature, and key_pair_id
            guid: GUID of the episode
            
        Returns:
            Dict: Stream information
        """
        # Ensure token is valid before making request
        if not self.check_token_valid():
            logger.error("Failed to get valid token for streams request")
            raise ValueError("No valid authentication token available")
            
        bucket = cms_data.get('bucket', '')
        policy = cms_data.get('policy', '')
        signature = cms_data.get('signature', '')
        key_pair_id = cms_data.get('key_pair_id', '')
        
        stream_url = f'https://cr-play-service.prd.crunchyrollsvc.com/v1/{guid}/web/chrome/play'
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'User-Agent': self.config.USER_AGENT
        }

        params = {
            'Policy': policy,
            'Signature': signature,
            'Key-Pair-Id': key_pair_id,
            'locale': locale
        }
        
        # Basic retry logic
        max_retries = 3
        
        for retry in range(max_retries + 1):
            try:
                response = requests.get(stream_url, headers=headers, cookies=self.cookies, params=params)
                
                # Handle too many active streams
                if (response.status_code in [400, 403, 420]) and retry < max_retries:
                    try:
                        error_data = response.json()
                        if 'error' in error_data and error_data['error'] == 'TOO_MANY_ACTIVE_STREAMS' and 'activeStreams' in error_data:
                            logger.warning("Too many active streams. Cleaning up old streams.")
                            for stream in error_data['activeStreams']:
                                if 'token' in stream and stream.get('active', False):
                                    content_id = stream.get('episodeIdentity', '')
                                    token = stream.get('token', '')
                                    logger.info(f"Cleaning up active stream: {content_id}")
                                    self.delete_streams(content_id, token)
                            # Wait briefly before retrying
                            time.sleep(1)
                            continue
                    except (ValueError, KeyError, json.JSONDecodeError):
                        pass
                
                # Handle login expiration
                if response.status_code == 401 and retry < max_retries:
                    logger.warning("Access token expired. Refreshing token.")
                    if self.refresh_access_token():
                        headers['Authorization'] = f'Bearer {self.access_token}'
                        time.sleep(1)
                        continue
                
                # If we get a successful response
                if response.status_code == 200:
                    streams_data = response.json()
                    save_json(streams_data, 'streams.json', self.json_dir)
                    logger.info("Stream information retrieved successfully")
                    return streams_data
                
                # For other errors, retry if we have retries left
                if retry < max_retries:
                    logger.warning(f"HTTP error {response.status_code}. Retrying in 2 seconds...")
                    time.sleep(2)
                    continue
                
                # If we've exhausted retries, raise the error
                response.raise_for_status()
                
            except requests.exceptions.HTTPError as e:
                logger.error(f"Failed to get streams: {str(e)}")
                if 'response' in locals() and response:
                    logger.error(f"Response: {response.status_code} {response.text}")
                if retry < max_retries:
                    time.sleep(2)
                    continue
                raise
            except Exception as e:
                logger.error(f"Failed to get streams: {str(e)}")
                if retry < max_retries:
                    time.sleep(2)
                    continue
                raise
        
        # If we've exhausted all retries
        logger.error("Exhausted all retries for getting stream information")
        if 'response' in locals() and response:
            raise requests.exceptions.HTTPError(f"{response.status_code} Client Error for url: {response.url}", response=response)
        else:
            raise Exception("Failed to get streams after multiple retries")

    def delete_streams(self, guid: str, video_token: str, suppress_errors=False) -> Dict:
        """
        Delete stream from server (cleanup)
        
        Args:
            guid: GUID of the episode
            video_token: Video token from stream information
            suppress_errors: Whether to suppress error logging (used during cleanup)
            
        Returns:
            Dict: Result of the delete operation
        """
        # Check token validity first
        self.check_token_valid()
        
        # Direct deletion URL
        delstream_url = f'https://cr-play-service.prd.crunchyrollsvc.com/v1/token/{guid}/{video_token}'
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'User-Agent': self.config.USER_AGENT
        }
        
        # Simple retry logic with minimal waits
        max_retries = 1  # Reduced from 2 to 1 for faster cleanup
        
        for retry in range(max_retries + 1):
            try:
                if not suppress_errors:
                    logger.info(f"Deleting stream for {guid}")
                response = requests.delete(delstream_url, headers=headers, cookies=self.cookies)
                
                if response.status_code in [200, 204, 404]:  # 404 = already deleted, which is also good
                    if not suppress_errors and response.status_code != 404:
                        logger.info("Stream deleted successfully")
                    return {"status": "deleted", "message": "Stream deleted successfully."}
                elif response.status_code == 401 and retry < max_retries:
                    # Login expired - refresh and retry
                    if self.refresh_access_token():
                        headers['Authorization'] = f'Bearer {self.access_token}'
                        continue
                elif retry < max_retries:
                    # For any other error, retry once
                    continue
                
                # If we get here, all retries failed
                if not suppress_errors:
                    logger.error(f"Failed to delete stream: {response.status_code}")
                return {"status": "error", "message": f"Failed to delete stream: {response.status_code}"}
                    
            except Exception as e:
                if not suppress_errors:
                    logger.error(f"Error deleting stream: {str(e)}")
                if retry < max_retries:
                    continue
                return {"status": "error", "message": f"Error deleting stream: {str(e)}"}
        
        return {"status": "error", "message": "Failed to delete stream after retries"} 