# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    admin_firmware_import.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""
Admin view for importing firmware images from GitHub Release ZIP archives.
Supports both local ZIP upload and direct GitHub API import.
"""

import os
import re
import zipfile
import hashlib
import tempfile
import logging
from typing import Dict, List, Tuple, Optional
from io import BytesIO

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.http import JsonResponse, HttpResponse
from django.utils.translation import gettext_lazy as _
from django.conf import settings
import requests

from iot.models import FirmwareImage

logger = logging.getLogger(__name__)

# Environment name mapping (6.3)
ENVIRONMENT_MAPPING = {
    'heltec_wifi_lora_32_V3': 'Heltec WiFi LoRa 32 V3',
    'heltec_wifi_lora_32_V2': 'Heltec WiFi LoRa 32 V2',
    'wemos_d1_mini32': 'Wemos D1 Mini32',
}

# Supported environments
SUPPORTED_ENVIRONMENTS = list(ENVIRONMENT_MAPPING.keys())

# File pattern: mcc-esp32-<environment>-<version>.bin
FILENAME_PATTERN = re.compile(
    r'^mcc-esp32-(heltec_wifi_lora_32_V3|heltec_wifi_lora_32_V2|wemos_d1_mini32)-(\d+\.\d+\.\d+)\.bin$'
)


def get_environment_display_name(env: str) -> str:
    """Get human-readable environment name."""
    return ENVIRONMENT_MAPPING.get(env, env)


def parse_filename(filename: str) -> Optional[Tuple[str, str]]:
    """
    Parse firmware filename to extract environment and version.
    
    Returns: (environment, version) or None if invalid
    """
    match = FILENAME_PATTERN.match(filename)
    if match:
        return match.group(1), match.group(2)
    return None

    
def calculate_checksum(file_data: bytes, algorithm: str = 'md5') -> str:
    """Calculate checksum for file data."""
    if algorithm == 'md5':
        return hashlib.md5(file_data).hexdigest()
    elif algorithm == 'sha256':
        return hashlib.sha256(file_data).hexdigest()
            else:
        raise ValueError(f"Unsupported algorithm: {algorithm}")


def read_checksum_file(zip_file: zipfile.ZipFile, checksum_filename: str) -> Optional[str]:
    """Read checksum from .md5 or .sha256 file."""
    try:
        with zip_file.open(checksum_filename, 'r') as f:
            content = f.read().decode('utf-8').strip()
            # Checksum files format: "hash  filename" or just "hash"
            parts = content.split()
            return parts[0] if parts else None
    except KeyError:
        return None
    except Exception as e:
        logger.warning(f"Error reading checksum file {checksum_filename}: {e}")
        return None


def validate_checksums(
    bin_data: bytes,
    expected_md5: Optional[str],
    expected_sha256: Optional[str]
) -> Tuple[bool, List[str]]:
    """
    Validate MD5 and SHA256 checksums.
    
    Returns: (is_valid, list_of_errors)
    """
    errors = []
    
    if expected_md5:
        actual_md5 = calculate_checksum(bin_data, 'md5')
        if actual_md5 != expected_md5:
            errors.append(_("MD5-Prüfsumme stimmt nicht überein: erwartet {}, berechnet {}").format(
                expected_md5, actual_md5
            ))
    
    if expected_sha256:
        actual_sha256 = calculate_checksum(bin_data, 'sha256')
        if actual_sha256 != expected_sha256:
            errors.append(_("SHA256-Prüfsumme stimmt nicht überein: erwartet {}, berechnet {}").format(
                expected_sha256, actual_sha256
            ))
    
    return len(errors) == 0, errors


def extract_firmware_files_from_zip(zip_file: zipfile.ZipFile) -> List[Dict]:
    """
    Extract and parse firmware files from ZIP archive.
    
    Returns: List of firmware info dicts
    """
    firmware_files = []
    
    # Get all .bin files (exclude checksum files)
    bin_files = [
        f for f in zip_file.namelist() 
        if f.endswith('.bin') 
        and not f.endswith('.md5') 
        and not f.endswith('.sha256')
        and 'mcc-esp32' in f  # Ensure it's a firmware file
    ]
    
    for bin_filename in bin_files:
        # Parse filename
        parsed = parse_filename(os.path.basename(bin_filename))
        if not parsed:
            logger.warning(f"Invalid firmware filename: {bin_filename}")
            continue
        
        environment, version = parsed
        
        # Read binary data
        try:
            with zip_file.open(bin_filename, 'r') as f:
                bin_data = f.read()
        except Exception as e:
            logger.error(f"Error reading {bin_filename}: {e}")
            continue
        
        # Validate file size (ESP32 firmware should be at least several KB)
        if len(bin_data) < 1000:
            logger.warning(f"Skipping {bin_filename}: File too small ({len(bin_data)} bytes), might be a checksum file")
            continue
        
        # Get checksum files
        md5_filename = bin_filename + '.md5'
        sha256_filename = bin_filename + '.sha256'
        
        expected_md5 = read_checksum_file(zip_file, md5_filename)
        expected_sha256 = read_checksum_file(zip_file, sha256_filename)
        
        # Validate checksums
        is_valid, errors = validate_checksums(bin_data, expected_md5, expected_sha256)
        
        firmware_info = {
            'filename': os.path.basename(bin_filename),
            'environment': environment,
            'environment_display': get_environment_display_name(environment),
            'version': version,
            'data': bin_data,
            'size': len(bin_data),
            'expected_md5': expected_md5,
            'expected_sha256': expected_sha256,
            'checksum_valid': is_valid,
            'checksum_errors': errors,
        }
        
        firmware_files.append(firmware_info)
    
    return firmware_files


def extract_firmware_files_from_assets(assets_dict: Dict[str, bytes]) -> List[Dict]:
    """
    Extract and parse firmware files from GitHub Release assets.
    
    Args:
        assets_dict: Dictionary mapping filename to file content (bytes)
    
    Returns: List of firmware info dicts
    """
    firmware_files = []
    
    # Get all .bin files (exclude checksum files that might end with .bin)
    bin_files = {
        name: data for name, data in assets_dict.items()
        if name.endswith('.bin') 
        and 'mcc-esp32' in name
        and not name.endswith('.md5.bin')  # Exclude any misnamed files
        and not name.endswith('.sha256.bin')
        and len(data) > 1000  # ESP32 firmware should be at least several KB
    }
    
    for bin_filename, bin_data in bin_files.items():
                    # Parse filename
        parsed = parse_filename(bin_filename)
        if not parsed:
            logger.warning(f"Invalid firmware filename: {bin_filename}")
                        continue
                    
        environment, version = parsed
                        
        # Get checksum files
        md5_filename = bin_filename + '.md5'
        sha256_filename = bin_filename + '.sha256'
        
        expected_md5 = None
        expected_sha256 = None
        
        # Read checksums from assets
        if md5_filename in assets_dict:
            checksum_content = assets_dict[md5_filename].decode('utf-8').strip()
            parts = checksum_content.split()
            expected_md5 = parts[0] if parts else None
                        
        if sha256_filename in assets_dict:
            checksum_content = assets_dict[sha256_filename].decode('utf-8').strip()
            parts = checksum_content.split()
            expected_sha256 = parts[0] if parts else None
        
        # Validate checksums
        is_valid, errors = validate_checksums(bin_data, expected_md5, expected_sha256)
        
        firmware_info = {
            'filename': bin_filename,
            'environment': environment,
            'environment_display': get_environment_display_name(environment),
            'version': version,
            'data': bin_data,
            'size': len(bin_data),
            'expected_md5': expected_md5,
            'expected_sha256': expected_sha256,
            'checksum_valid': is_valid,
            'checksum_errors': errors,
        }
        
        firmware_files.append(firmware_info)
    
    return firmware_files


def check_duplicates(firmware_files: List[Dict], overwrite: bool = False) -> Tuple[List[str], List[Dict]]:
    """
    Check for duplicate firmware versions.
    
    Returns: (list_of_warnings, list_of_files_to_import)
    """
    warnings = []
    files_to_import = []
    
    for fw_info in firmware_files:
        # Check if firmware with same version and environment exists
        existing = FirmwareImage.objects.filter(
            version=fw_info['version'],
            environment=fw_info['environment']
        ).first()
        
        if existing:
            if overwrite:
                warnings.append(_("Firmware {} ({}) wird überschrieben").format(
                    fw_info['version'], fw_info['environment_display']
                ))
                # Mark existing as inactive
                existing.is_active = False
                existing.save()
                files_to_import.append(fw_info)
            else:
                warnings.append(_("Firmware {} ({}) existiert bereits und wird übersprungen").format(
                    fw_info['version'], fw_info['environment_display']
                ))
        else:
            files_to_import.append(fw_info)
    
    return warnings, files_to_import


def download_github_release_assets(repo_owner: str, repo_name: str, tag: str, github_token: Optional[str] = None) -> Tuple[Optional[Dict[str, bytes]], Optional[str]]:
    """
    Download individual release assets from GitHub Release (6.1).
    
    Downloads all .bin, .md5, and .sha256 files from the release assets.
    Returns them as a dictionary mapping filename to content.
    
    Returns: (dict of {filename: bytes} or None on error, error message or None)
    """
    headers = {}
    if github_token:
        headers['Authorization'] = f"token {github_token}"
    else:
        # GitHub allows anonymous access to public repos, but rate limits are stricter
        headers['Accept'] = 'application/vnd.github.v3+json'
    
    try:
        # Get release info to find assets
        api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/tags/{tag}"
        api_response = requests.get(api_url, headers=headers, timeout=30)
        
        if api_response.status_code == 404:
            # Try without 'v' prefix
            if tag.startswith('v'):
                tag_without_v = tag[1:]
                api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/tags/{tag_without_v}"
                api_response = requests.get(api_url, headers=headers, timeout=30)
                if api_response.status_code == 200:
                    tag = tag_without_v
            elif not tag.startswith('v'):
                # Try with 'v' prefix
                tag_with_v = f"v{tag}"
                api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/tags/{tag_with_v}"
                api_response = requests.get(api_url, headers=headers, timeout=30)
                if api_response.status_code == 200:
                    tag = tag_with_v
        
        if api_response.status_code != 200:
            error_msg = f"Release nicht gefunden. Status: {api_response.status_code}"
            if api_response.status_code == 404:
                error_msg = f"Release mit Tag '{tag}' nicht gefunden. Bitte prüfen Sie Repository, Owner und Tag."
            elif api_response.status_code == 401:
                error_msg = "Authentifizierung fehlgeschlagen. Bitte prüfen Sie den GitHub Token."
            elif api_response.status_code == 403:
                error_msg = "Zugriff verweigert. Möglicherweise ist das Repository privat oder der Token hat keine Berechtigung."
            else:
                try:
                    error_data = api_response.json()
                    error_msg = error_data.get('message', error_msg)
                except:
                    pass
            logger.error(f"GitHub API error: {error_msg}")
            return None, error_msg
        
        release_data = api_response.json()
        assets = release_data.get('assets', [])
        
        if not assets:
            error_msg = "Keine Assets in diesem Release gefunden. Bitte stellen Sie sicher, dass der GitHub Actions Workflow die Firmware-Dateien hochgeladen hat."
            logger.error(error_msg)
            return None, error_msg
        
        # Filter for firmware-related assets (.bin, .md5, .sha256)
        firmware_assets = [
            asset for asset in assets
            if asset['name'].endswith(('.bin', '.md5', '.sha256')) and 'mcc-esp32' in asset['name']
        ]
        
        if not firmware_assets:
            error_msg = "Keine Firmware-Assets (.bin, .md5, .sha256) in diesem Release gefunden."
            logger.error(error_msg)
            return None, error_msg
        
        logger.info(f"Found {len(firmware_assets)} firmware assets in release")
        
        # Download each asset
        assets_dict = {}
        for asset in firmware_assets:
            asset_name = asset['name']
            download_url = asset['browser_download_url']
            
            logger.info(f"Downloading asset: {asset_name}")
            asset_response = requests.get(download_url, headers=headers, timeout=120, stream=True)
            asset_response.raise_for_status()
            
            # Read content in chunks
            content = b''
            for chunk in asset_response.iter_content(chunk_size=8192):
                if chunk:
                    content += chunk
            
            assets_dict[asset_name] = content
            logger.info(f"Downloaded {asset_name}: {len(content)} bytes")
        
        return assets_dict, None
            
    except requests.exceptions.Timeout:
        error_msg = "Zeitüberschreitung beim Herunterladen der Assets."
        logger.error(error_msg)
        return None, error_msg
    except requests.exceptions.ConnectionError as e:
        error_msg = f"Verbindungsfehler: {str(e)}"
        logger.error(f"Connection error downloading GitHub release assets: {e}")
        return None, error_msg
    except requests.exceptions.HTTPError as e:
        error_msg = f"HTTP-Fehler: {e.response.status_code} - {str(e)}"
        logger.error(f"HTTP error downloading GitHub release assets: {e}")
        return None, error_msg
    except requests.exceptions.RequestException as e:
        error_msg = f"Fehler beim Herunterladen: {str(e)}"
        logger.error(f"Error downloading GitHub release assets: {e}")
        return None, error_msg
    except Exception as e:
        error_msg = f"Unerwarteter Fehler: {str(e)}"
        logger.exception(f"Unexpected error downloading GitHub release assets: {e}")
        return None, error_msg


@staff_member_required
@require_http_methods(["GET", "POST"])
def import_firmware_from_zip(request):
    """
    Import firmware images from GitHub Release ZIP archive.
    
    Supports:
    - Local ZIP file upload
    - Direct GitHub Release download (6.1)
    """
    if request.method == 'GET':
        # Show import form
        return render(request, 'admin/iot/firmware_import.html', {
            'title': _('Firmware aus GitHub Release ZIP importieren'),
            'supported_environments': [
                {'key': env, 'display': get_environment_display_name(env)}
                for env in SUPPORTED_ENVIRONMENTS
            ],
        })
    
    # POST: Process import
    import_mode = request.POST.get('import_mode', 'upload')
    overwrite_duplicates = request.POST.get('overwrite_duplicates') == 'on'
    mark_as_stable = request.POST.get('mark_as_stable') == 'on'
    
    errors = []
    warnings = []
    imported = []
    
    try:
        zip_data = None
        
        firmware_files = []
        
        if import_mode == 'github':
            # Direct GitHub import (6.1) - Download individual assets
            repo_owner = request.POST.get('repo_owner', '').strip()
            repo_name = request.POST.get('repo_name', '').strip()
            tag = request.POST.get('tag', '').strip()
            github_token = request.POST.get('github_token', '').strip() or None
            
            if not all([repo_owner, repo_name, tag]):
                errors.append(_("Repository-Owner, Repository-Name und Tag sind erforderlich"))
            else:
                messages.info(request, _("Lade Release-Assets von GitHub herunter..."))
                assets_dict, error_msg = download_github_release_assets(repo_owner, repo_name, tag, github_token)
                
                if not assets_dict:
                    if error_msg:
                        errors.append(error_msg)
                    else:
                        errors.append(_("Fehler beim Herunterladen des GitHub Releases"))
                else:
                    # Extract firmware files from assets
                    firmware_files = extract_firmware_files_from_assets(assets_dict)
        
        elif import_mode == 'upload':
            # Local ZIP upload
            if 'zip_file' not in request.FILES:
                errors.append(_("Bitte wählen Sie eine ZIP-Datei aus"))
            else:
                zip_file_obj = request.FILES['zip_file']
                if not zip_file_obj.name.endswith('.zip'):
                    errors.append(_("Die Datei muss eine ZIP-Datei sein"))
                else:
                    zip_data = zip_file_obj.read()
                    
                    # Extract firmware files from ZIP
                    # GitHub source archives have a top-level directory like "repo-name-tag/"
                    # We need to look for release/ directory inside
                    with zipfile.ZipFile(BytesIO(zip_data), 'r') as zip_file:
                        # Find the release directory in the archive
                        release_dir = None
                        for name in zip_file.namelist():
                            # Look for release/ directory (could be at root or in subdirectory)
                            if 'release/' in name and name.endswith('/'):
                                # Extract the base path
                                parts = name.split('release/')
                                if len(parts) > 1:
                                    release_dir = parts[0] + 'release/'
                                    break
                        
                        if release_dir:
                            # Create a new ZIP with files from release/ directory
                            temp_zip = BytesIO()
                            with zipfile.ZipFile(temp_zip, 'w', zipfile.ZIP_DEFLATED) as new_zip:
                                for name in zip_file.namelist():
                                    if name.startswith(release_dir) and not name.endswith('/'):
                                        # Extract file and add to new ZIP with relative path
                                        rel_path = name[len(release_dir):]
                                        new_zip.writestr(rel_path, zip_file.read(name))
                            
                            temp_zip.seek(0)
                            firmware_files = extract_firmware_files_from_zip(zipfile.ZipFile(temp_zip, 'r'))
                        else:
                            # Fallback: try to extract from root or any location
                            firmware_files = extract_firmware_files_from_zip(zip_file)
        
        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'admin/iot/firmware_import.html', {
                'title': _('Firmware aus GitHub Release ZIP importieren'),
                'supported_environments': [
                    {'key': env, 'display': get_environment_display_name(env)}
                    for env in SUPPORTED_ENVIRONMENTS
                ],
            })
        
        if not firmware_files:
            messages.error(request, _("Keine gültigen Firmware-Dateien im ZIP-Archiv gefunden"))
            return render(request, 'admin/iot/firmware_import.html', {
                'title': _('Firmware aus GitHub Release ZIP importieren'),
                'supported_environments': [
                    {'key': env, 'display': get_environment_display_name(env)}
                    for env in SUPPORTED_ENVIRONMENTS
                ],
            })
        
        # Check for checksum errors
        checksum_errors = [fw for fw in firmware_files if not fw['checksum_valid']]
        if checksum_errors:
            for fw in checksum_errors:
                for error in fw['checksum_errors']:
                    errors.append(f"{fw['filename']}: {error}")
                        
                        # Check for duplicates
        dup_warnings, files_to_import = check_duplicates(firmware_files, overwrite_duplicates)
        warnings.extend(dup_warnings)
        
        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'admin/iot/firmware_import.html', {
                'title': _('Firmware aus GitHub Release ZIP importieren'),
                'supported_environments': [
                    {'key': env, 'display': get_environment_display_name(env)}
                    for env in SUPPORTED_ENVIRONMENTS
                ],
            })
        
        # Import firmware images
        with transaction.atomic():
            for fw_info in files_to_import:
                        # Create FirmwareImage
                firmware = FirmwareImage(
                    name=f"Firmware {fw_info['version']} ({fw_info['environment_display']})",
                    version=fw_info['version'],
                    environment=fw_info['environment'],
                    description=_("Importiert aus GitHub Release ZIP"),
                    is_active=True,
                    is_stable=mark_as_stable,
                )
                
                # Save binary data to file
                filename = f"mcc-esp32-{fw_info['environment']}-{fw_info['version']}.bin"
                
                # Validate that we have actual binary data (not a checksum file)
                data_size = len(fw_info['data'])
                if data_size < 10000:  # ESP32 firmware should be at least 10 KB
                    errors.append(_("Firmware-Datei {} ist zu klein ({} Bytes). Möglicherweise wurde eine Checksum-Datei statt der .bin-Datei importiert.").format(
                        fw_info['filename'], data_size
                    ))
                    continue
                
                # Create BytesIO and ensure it's at the beginning
                file_data = BytesIO(fw_info['data'])
                file_data.seek(0)
                
                # Save file
                firmware.firmware_file.save(
                    filename,
                    file_data,
                    save=False
                )
                
                # Set file size BEFORE saving
                firmware.file_size = data_size
                
                # Save the model
                firmware.save()
                
                # Verify file was saved correctly
                import os
                if firmware.firmware_file and firmware.firmware_file.path:
                    saved_file_size = os.path.getsize(firmware.firmware_file.path)
                    if saved_file_size != data_size:
                        logger.error(
                            f"File size mismatch after save: expected {data_size}, got {saved_file_size} "
                            f"for {fw_info['filename']}"
                        )
                        errors.append(_("Fehler beim Speichern der Firmware-Datei {}: Dateigröße stimmt nicht überein").format(
                            fw_info['filename']
                        ))
                        # Delete the incomplete file
                        try:
                            os.remove(firmware.firmware_file.path)
                        except:
                            pass
                        continue
                    
                    logger.info(f"Successfully saved firmware {fw_info['filename']}: {saved_file_size} bytes")
                
                # Set checksums
                firmware.checksum_md5 = fw_info['expected_md5']
                firmware.checksum_sha256 = fw_info['expected_sha256']
                
                firmware.save()
                imported.append(firmware)
        
        # Success messages
        if imported:
            messages.success(request, _("{} Firmware-Image(s) erfolgreich importiert").format(len(imported)))
            for fw in imported:
                messages.info(request, _("• {} ({})").format(fw.name, fw.version))
                
                if warnings:
                    for warning in warnings:
                        messages.warning(request, warning)
        
        # Redirect to firmware list
        from django.urls import reverse
        return redirect(reverse('admin:iot_firmwareimage_changelist'))
        
    except zipfile.BadZipFile:
        messages.error(request, _("Ungültiges ZIP-Archiv"))
        return render(request, 'admin/iot/firmware_import.html', {
            'title': _('Firmware aus GitHub Release ZIP importieren'),
            'supported_environments': [
                {'key': env, 'display': get_environment_display_name(env)}
                for env in SUPPORTED_ENVIRONMENTS
            ],
        })
    except Exception as e:
        logger.exception("Error importing firmware from ZIP")
        messages.error(request, _("Fehler beim Import: {}").format(str(e)))
        return render(request, 'admin/iot/firmware_import.html', {
            'title': _('Firmware aus GitHub Release ZIP importieren'),
            'supported_environments': [
                {'key': env, 'display': get_environment_display_name(env)}
                for env in SUPPORTED_ENVIRONMENTS
            ],
        })
