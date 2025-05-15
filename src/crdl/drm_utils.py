"""DRM utilities for Crunchyroll downloader"""
import base64
import binascii
import logging
import re
from typing import Optional, Dict, List

logger = logging.getLogger("CrunchyrollDownloader")

def build_pssh_from_kid(kid: str) -> str:
    """
    Build a PSSH box from a KID
    
    Args:
        kid: Key ID in hex format
    
    Returns:
        str: Base64 encoded PSSH box
    """
    try:
        # Convert KID from hex to bytes
        kid_bytes = bytes.fromhex(kid)
        
        # PSSH box header (size + 'pssh' + version + flags)
        pssh_header = bytearray([
            0x00, 0x00, 0x00, 0x00,  # Size (to be filled later)
            0x70, 0x73, 0x73, 0x68,  # 'pssh'
            0x00, 0x00, 0x00, 0x00   # Version 0 + flags
        ])
        
        # Widevine system ID: edef8ba9-79d6-4ace-a3c8-27dcd51d21ed
        widevine_system_id = bytearray([
            0xed, 0xef, 0x8b, 0xa9, 0x79, 0xd6, 0x4a, 0xce,
            0xa3, 0xc8, 0x27, 0xdc, 0xd5, 0x1d, 0x21, 0xed
        ])
        
        # Data field - simplified version that includes KID
        # Format: [size][protobuf_id][size][kid]
        data = bytearray([
            0x00, 0x00, 0x00, 0x12,  # Data length (18 bytes)
            0x12, 0x10                # Protobuf field tag for KID
        ])
        data.extend(kid_bytes)        # Add the KID itself
        
        # Combine all parts
        pssh_box = pssh_header + widevine_system_id + data
        
        # Update size (big endian)
        size = len(pssh_box)
        pssh_box[0] = (size >> 24) & 0xFF
        pssh_box[1] = (size >> 16) & 0xFF
        pssh_box[2] = (size >> 8) & 0xFF
        pssh_box[3] = size & 0xFF
        
        # Encode as base64
        pssh_base64 = base64.b64encode(pssh_box).decode('ascii')
        return pssh_base64
        
    except Exception as e:
        logger.error(f"Error building PSSH from KID: {str(e)}", exc_info=True)
        return None

def find_kid_in_pssh_data(data: bytes) -> Optional[str]:
    """
    Find KID in PSSH data section, which might be in protobuf format
    
    Args:
        data: PSSH data bytes
        
    Returns:
        Optional[str]: KID in hex format, or None if not found
    """
    try:
        # Look for the protobuf pattern for KID: field tag 0x12 0x10 followed by 16 bytes
        # Field tag 0x12 = field number 2, wire type 2 (length-delimited)
        # 0x10 = length 16
        marker = b'\x12\x10'
        pos = data.find(marker)
        
        if pos != -1 and len(data) >= pos + 18:  # marker (2) + KID (16)
            kid = data[pos + 2:pos + 18].hex()
            return kid
            
        # Alternative pattern sometimes used
        marker = b'\x22\x10'  # Field 4, wire type 2, length 16
        pos = data.find(marker)
        
        if pos != -1 and len(data) >= pos + 18:
            kid = data[pos + 2:pos + 18].hex()
            return kid
            
        # Search for any 16-byte sequence that might be a KID
        # This is a fallback and less reliable
        if len(data) >= 16:
            for i in range(len(data) - 16 + 1):
                # Check if this might be a KID by examining surrounding bytes
                # Often a KID is preceded by a tag byte and length byte
                if i >= 2 and (data[i-2] & 0x07) == 2 and data[i-1] == 0x10:
                    kid_candidate = data[i:i+16].hex()
                    return kid_candidate
        
        return None
        
    except Exception as e:
        logger.error(f"Error finding KID in PSSH data: {str(e)}", exc_info=True)
        return None

def create_pssh_object(pssh_base64=None, kid_hex=None):
    """
    Create a PSSH object from either base64 PSSH or KID
    
    Args:
        pssh_base64: Base64 encoded PSSH box
        kid_hex: KID in hex format
        
    Returns:
        PSSH: PSSH object
    """
    try:
        # Import Widevine CDM modules
        from pywidevine.pssh import PSSH
        
        # If PSSH is provided, try to create object directly
        if pssh_base64:
            try:
                return PSSH(pssh_base64)
            except Exception as e:
                logger.error(f"Failed to create PSSH from base64: {str(e)}")
        
        # If KID is provided, try to create new PSSH
        if kid_hex:
            kid_bytes = bytes.fromhex(kid_hex)
            
            # Try different approaches based on PyWidevine version
            try:
                # New style (PSSH.new method)
                return PSSH.new(kid_bytes)
            except (AttributeError, TypeError) as e:
                logger.warning(f"PSSH.new failed: {str(e)}")
                # Older versions might expect different parameters
                try:
                    return PSSH(kid_ids=[kid_bytes])
                except (TypeError, ValueError) as e:
                    logger.warning(f"PSSH constructor with kid_ids failed: {str(e)}")
            
            # Try using mp4parse module if available
            try:
                import mp4parse
                logger.info("Trying to create PSSH using mp4parse module")
                
                # Create an init data with the proper format
                pssh_data = mp4parse.create_pssh_init_data([kid_bytes.hex()])
                return PSSH(pssh_data)
            except ImportError:
                logger.warning("mp4parse module not available")
            except Exception as e:
                logger.warning(f"mp4parse creation failed: {str(e)}")
            
            # If all else fails, manually construct a PSSH object with pssh_data
            try:
                # Widevine system ID
                system_id = bytes.fromhex("edef8ba979d64acea3c827dcd51d21ed")
                
                # Create a PSSH v1 box
                pssh_v1_data = bytearray([
                    0x00, 0x00, 0x00, 0x34,  # Size (52 bytes)
                    0x70, 0x73, 0x73, 0x68,  # 'pssh'
                    0x01, 0x00, 0x00, 0x00,  # Version 1 + flags
                ])
                
                # Add system ID
                pssh_v1_data.extend(system_id)
                
                # KID count (1)
                pssh_v1_data.extend([0x00, 0x00, 0x00, 0x01])
                
                # Add KID
                pssh_v1_data.extend(kid_bytes)
                
                # Data size (0)
                pssh_v1_data.extend([0x00, 0x00, 0x00, 0x00])
                
                # Convert to base64
                pssh_base64_new = base64.b64encode(pssh_v1_data).decode('ascii')
                logger.info(f"Created manual PSSH: {pssh_base64_new}")
                
                # Try to create PSSH object
                return PSSH(pssh_base64_new)
            except Exception as e:
                logger.error(f"Failed to manually create PSSH: {str(e)}")
        
        return None
    except ImportError:
        logger.error("Failed to import pywidevine modules. Please install them first.")
        return None
    except Exception as e:
        logger.error(f"Failed to create PSSH object: {str(e)}")
        return None

def decode_pssh(pssh_base64):
    """
    Decode a base64 PSSH box to extract the KID
    
    Args:
        pssh_base64: Base64 encoded PSSH box
        
    Returns:
        dict: Dictionary containing KID
    """
    try:
        logger.info("Decoding PSSH")
        
        # Validate and decode input
        if not pssh_base64 or not isinstance(pssh_base64, str):
            logger.error("Invalid PSSH: not a string or empty")
            return None
            
        try:
            pssh_binary = base64.b64decode(pssh_base64)
        except Exception as e:
            logger.error(f"Failed to decode base64 PSSH: {str(e)}")
            return None
        
        # Check PSSH box format
        if len(pssh_binary) < 32:
            logger.error("PSSH box too small")
            return None
        
        # Check for the PSSH box header (starts with 'pssh')
        if pssh_binary[4:8] != b'pssh':
            logger.error("Not a valid PSSH box")
            return None
        
        # Check for Widevine system ID: edef8ba9-79d6-4ace-a3c8-27dcd51d21ed
        widevine_system_id = b'\xed\xef\x8b\xa9\x79\xd6\x4a\xce\xa3\xc8\x27\xdc\xd5\x1d\x21\xed'
        found_system_id = False
        
        # Check different PSSH versions
        pssh_version = pssh_binary[8] & 0xFF
        logger.info(f"PSSH version: {pssh_version}")
        
        kid = None
        
        if pssh_version == 0:
            # Version 0
            logger.info("Processing PSSH version 0")
            system_id = pssh_binary[12:28]
            if system_id == widevine_system_id:
                found_system_id = True
                logger.info("Found Widevine system ID")
                
                # Extract KID if possible - but this depends on the content of the data field
                # We'll try to find KID patterns in the data
                data_size = int.from_bytes(pssh_binary[28:32], byteorder='big')
                logger.info(f"Data size: {data_size}")
                
                if data_size >= 16:
                    # Attempt to find patterns of 16-byte groups that might be KIDs
                    data = pssh_binary[32:32+data_size]
                    
                    # Try to interpret as Widevine PSSH proto format
                    try:
                        kid = find_kid_in_pssh_data(data)
                        if kid:
                            logger.info(f"Found KID in PSSH data: {kid}")
                    except Exception as e:
                        logger.error(f"Error finding KID in data: {str(e)}")
            
        elif pssh_version == 1:
            # Version 1
            logger.info("Processing PSSH version 1")
            system_id = pssh_binary[12:28]
            if system_id == widevine_system_id:
                found_system_id = True
                logger.info("Found Widevine system ID")
                
                # KID Count
                kid_count = int.from_bytes(pssh_binary[28:32], byteorder='big')
                logger.info(f"KID count: {kid_count}")
                
                if kid_count > 0:
                    # For simplicity, just use the first KID
                    kid = pssh_binary[32:48].hex()
                    logger.info(f"First KID: {kid}")
        
        if not found_system_id:
            logger.warning("Widevine system ID not found in PSSH")
        
        # If no KID found but we know it's Widevine, try to extract from data field
        if not kid and found_system_id:
            logger.info("Attempting to extract KID using alternative methods")
            
            # Find data field and try parsing as a protobuf message
            if pssh_version == 0:
                data_offset = 32
                data_size = int.from_bytes(pssh_binary[28:32], byteorder='big')
            else:  # version 1
                kid_count = int.from_bytes(pssh_binary[28:32], byteorder='big')
                data_offset = 32 + (kid_count * 16)
                if len(pssh_binary) > data_offset + 4:
                    data_size = int.from_bytes(pssh_binary[data_offset:data_offset+4], byteorder='big')
                    data_offset += 4
                else:
                    data_size = len(pssh_binary) - data_offset
            
            if data_size > 0 and data_offset + data_size <= len(pssh_binary):
                data = pssh_binary[data_offset:data_offset+data_size]
                try:
                    kid = find_kid_in_pssh_data(data)
                    if kid:
                        logger.info(f"Found KID using alternative method: {kid}")
                except Exception as e:
                    logger.error(f"Error finding KID with alternative method: {str(e)}")
        
        if not kid:
            logger.warning("No KID found in PSSH")
            # Return with empty KID - might still be usable for license requests
            return {'kid': None, 'pssh': pssh_base64}
        
        return {'kid': kid, 'pssh': pssh_base64}
        
    except Exception as e:
        logger.error(f"Error decoding PSSH: {str(e)}", exc_info=True)
        return None

def extract_mpd_info(mpd_content: str) -> Dict:
    """
    Extract DRM information from MPD content
    
    Args:
        mpd_content: MPD content as string
        
    Returns:
        Dict: Dictionary with PSSH, KID, and license URL
    """
    # Initialize result
    result = {
        'pssh': None,
        'kid': None,
        'license_url': None
    }
    
    # Extract PSSH from the MPD
    pssh_pattern = r'<cenc:pssh>([^<]+)</cenc:pssh>'
    pssh_match = re.search(pssh_pattern, mpd_content)
    
    if pssh_match:
        logger.info("Found PSSH in cenc:pssh element")
        result['pssh'] = pssh_match.group(1)
    else:
        # Try to find it in the non-standard Crunchyroll format
        cr_pssh_pattern = r'<ContentProtection.+?cenc:default_KID="([^"]+)".+?Widevine'
        cr_pssh_match = re.search(cr_pssh_pattern, mpd_content, re.DOTALL)
        
        if cr_pssh_match:
            logger.info("Found KID in ContentProtection element")
            kid = cr_pssh_match.group(1).replace('-', '')
            logger.info(f"KID: {kid}")
            result['kid'] = kid
            
            # Construct PSSH from KID
            pssh = build_pssh_from_kid(kid)
            if pssh:
                logger.info("Generated PSSH from KID")
                result['pssh'] = pssh
    
    # Find license URL
    license_pattern = r'<ContentProtection.+?value="com\.widevine\.alpha"[^>]*>.+?<cenc:default_KID>([^<]+)</cenc:default_KID>.+?<cenc:laurl>([^<]+)</cenc:laurl>'
    license_match = re.search(license_pattern, mpd_content, re.DOTALL)
    
    if license_match:
        logger.info("Found license URL in cenc:laurl element")
        kid = license_match.group(1).replace('-', '')
        result['kid'] = kid
        result['license_url'] = license_match.group(2)
    else:
        # Try to find it in extended media attribute
        mspr_pattern = r'mspr:licenseUrl="([^"]+)"'
        mspr_match = re.search(mspr_pattern, mpd_content)
        
        if mspr_match:
            logger.info("Found license URL in mspr:licenseUrl attribute")
            result['license_url'] = mspr_match.group(1)
        else:
            # Look for Crunchyroll's specific license URL format
            cr_license_pattern = r'<ContentProtection.+?value="com\.widevine\.alpha"[^>]*>.+?<cenc:pssh>[^<]+</cenc:pssh>'
            cr_license_match = re.search(cr_license_pattern, mpd_content, re.DOTALL)
            
            if cr_license_match:
                logger.info("Using default Crunchyroll license URL")
                result['license_url'] = "https://cr-license-proxy.prd.crunchyrollsvc.com/v1/license/widevine"
    
    # If still no license URL, use the default Crunchyroll one
    if not result['license_url']:
        logger.info("No license URL found, using default Crunchyroll license URL")
        result['license_url'] = "https://cr-license-proxy.prd.crunchyrollsvc.com/v1/license/widevine"
    
    # If PSSH found but no KID, try to decode PSSH to get KID
    if result['pssh'] and not result['kid']:
        logger.info("Decoding PSSH to extract KID")
        pssh_info = decode_pssh(result['pssh'])
        if pssh_info and pssh_info.get('kid'):
            result['kid'] = pssh_info['kid']
    
    return result 

def get_license_from_response(response_content):
    """
    Extract license from Crunchyroll/DRMToday license server response
    
    Args:
        response_content: Binary response content
        
    Returns:
        bytes: Decoded license data
    """
    import json
    import base64
    
    try:
        # First try to parse as JSON
        response_json = json.loads(response_content)
        
        # Check if the response contains a base64-encoded license field
        if 'license' in response_json:
            return base64.b64decode(response_json['license'])
        else:
            # Return the original response if no license field found
            return response_content
    except (json.JSONDecodeError, UnicodeDecodeError):
        # Not a JSON response, return as-is
        return response_content
    except Exception as e:
        logging.error(f"Error parsing license response: {str(e)}")
        return response_content 