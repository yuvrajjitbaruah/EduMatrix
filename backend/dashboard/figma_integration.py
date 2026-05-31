"""
Figma Integration Utilities for EduMatrix Platform
Provides server-side utilities for Figma API operations and asset management
"""

import re
import json
import logging
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse, parse_qs
from pathlib import Path

logger = logging.getLogger(__name__)


class FigmaIntegrationError(Exception):
    """Base exception for Figma integration errors"""
    pass


class FigmaAuthError(FigmaIntegrationError):
    """Raised when Figma API authentication fails"""
    pass


class FigmaNotFoundError(FigmaIntegrationError):
    """Raised when Figma file or node is not found"""
    pass


class FigmaRateLimitError(FigmaIntegrationError):
    """Raised when Figma API rate limit is exceeded"""
    pass


class FigmaNetworkError(FigmaIntegrationError):
    """Raised when network error occurs with Figma API"""
    pass


class FigmaIntegration:
    """
    Main class for Figma API integration and asset management
    """
    
    def __init__(self):
        self.api_base_url = "https://api.figma.com/v1"
        self.retry_attempts = 3
        self.retry_delay = 1.0
        
    def extract_file_key(self, figma_url: str) -> Optional[str]:
        """
        Extract file key from Figma URL
        
        Args:
            figma_url: Full Figma URL
            
        Returns:
            File key or None if invalid
        """
        try:
            pattern = r'figma\.com/(file|design)/([a-zA-Z0-9]+)'
            match = re.search(pattern, figma_url)
            return match.group(2) if match else None
        except Exception as e:
            logger.error(f"Error extracting file key: {e}")
            return None
    
    def extract_node_id(self, figma_url: str) -> Optional[str]:
        """
        Extract node ID from Figma URL
        
        Args:
            figma_url: Full Figma URL with node-id parameter
            
        Returns:
            Node ID or None if not found
        """
        try:
            parsed_url = urlparse(figma_url)
            query_params = parse_qs(parsed_url.query)
            node_id = query_params.get('node-id', [None])[0]
            return node_id.replace('-', ':') if node_id else None
        except Exception as e:
            logger.error(f"Error extracting node ID: {e}")
            return None
    
    def is_valid_file_key(self, file_key: str) -> bool:
        """
        Validate Figma file key format
        
        Args:
            file_key: File key to validate
            
        Returns:
            True if valid format
        """
        pattern = r'^[a-zA-Z0-9]+$'
        return bool(re.match(pattern, file_key)) and len(file_key) > 10
    
    def is_valid_node_id(self, node_id: str) -> bool:
        """
        Validate Figma node ID format
        
        Args:
            node_id: Node ID to validate
            
        Returns:
            True if valid format
        """
        pattern = r'^I?\d+[:|-]\d+(?:;\d+[:|-]\d+)*$'
        return bool(re.match(pattern, node_id))
    
    def generate_asset_filename(self, node_data: Dict, extension: str = 'svg') -> str:
        """
        Generate asset filename from node data
        
        Args:
            node_data: Node data from Figma API
            extension: File extension
            
        Returns:
            Generated filename
        """
        name = node_data.get('name', 'asset')
        # Sanitize name for filesystem
        sanitized = re.sub(r'[^a-z0-9]', '-', name.lower())
        sanitized = re.sub(r'-+', '-', sanitized).strip('-')
        
        node_id = node_data.get('id', '').replace(':', '-')
        return f"{sanitized}-{node_id}.{extension}"
    
    def parse_design_tokens(self, figma_data: Dict) -> Dict[str, Any]:
        """
        Parse design tokens from Figma styles
        
        Args:
            figma_data: Complete Figma file data
            
        Returns:
            Parsed design tokens
        """
        tokens = {
            'colors': {},
            'typography': {},
            'spacing': {},
            'shadows': {},
            'border_radius': {}
        }
        
        try:
            # Parse styles
            styles = figma_data.get('styles', {})
            for style_id, style in styles.items():
                style_type = style.get('styleType')
                style_name = style.get('name', f'style-{style_id}')
                
                if style_type == 'FILL':
                    tokens['colors'][style_name] = self._extract_color_value(style)
                elif style_type == 'TEXT':
                    tokens['typography'][style_name] = self._extract_text_style(style)
                elif style_type == 'EFFECT':
                    tokens['shadows'][style_name] = self._extract_effect_style(style)
            
            # Parse document nodes for spacing and border radius
            document = figma_data.get('document')
            if document:
                self._parse_node_properties(document, tokens)
                
        except Exception as e:
            logger.error(f"Error parsing design tokens: {e}")
        
        return tokens
    
    def _extract_color_value(self, style: Dict) -> str:
        """Extract color value from Figma style"""
        try:
            fills = style.get('fills', [])
            if fills and fills[0]:
                fill = fills[0]
                if fill.get('type') == 'SOLID':
                    color = fill.get('color', {})
                    r = int(color.get('r', 0) * 255)
                    g = int(color.get('g', 0) * 255)
                    b = int(color.get('b', 0) * 255)
                    alpha = fill.get('opacity', 1)
                    
                    if alpha < 1:
                        return f"rgba({r}, {g}, {b}, {alpha})"
                    else:
                        return f"rgb({r}, {g}, {b})"
        except Exception as e:
            logger.error(f"Error extracting color value: {e}")
        
        return '#000000'
    
    def _extract_text_style(self, style: Dict) -> Dict[str, str]:
        """Extract text style properties"""
        try:
            text_style = style.get('style', {})
            return {
                'font_family': text_style.get('fontFamily', 'Inter'),
                'font_size': f"{text_style.get('fontSize', 16)}px",
                'font_weight': str(text_style.get('fontWeight', 400)),
                'line_height': f"{text_style.get('lineHeightPx', 'normal')}px" if text_style.get('lineHeightPx') else 'normal',
                'letter_spacing': f"{text_style.get('letterSpacing', 0)}px" if text_style.get('letterSpacing') else 'normal'
            }
        except Exception as e:
            logger.error(f"Error extracting text style: {e}")
            return {}
    
    def _extract_effect_style(self, style: Dict) -> str:
        """Extract effect style (shadows, blurs)"""
        try:
            effects = style.get('effects', [])
            if effects and effects[0]:
                effect = effects[0]
                if effect.get('type') == 'DROP_SHADOW':
                    offset = effect.get('offset', {})
                    x = offset.get('x', 0)
                    y = offset.get('y', 0)
                    blur = effect.get('radius', 0)
                    spread = effect.get('spread', 0)
                    
                    color = effect.get('color', {})
                    r = int(color.get('r', 0) * 255)
                    g = int(color.get('g', 0) * 255)
                    b = int(color.get('b', 0) * 255)
                    a = color.get('a', 1)
                    
                    color_str = f"rgba({r}, {g}, {b}, {a})"
                    return f"{x}px {y}px {blur}px {spread}px {color_str}"
        except Exception as e:
            logger.error(f"Error extracting effect style: {e}")
        
        return 'none'
    
    def _parse_node_properties(self, node: Dict, tokens: Dict):
        """Parse node properties for spacing and border radius"""
        try:
            # Extract border radius
            corner_radius = node.get('cornerRadius')
            if corner_radius is not None:
                tokens['border_radius'][f'radius-{corner_radius}'] = f"{corner_radius}px"
            
            # Extract padding/spacing
            padding_left = node.get('paddingLeft')
            if padding_left is not None:
                tokens['spacing'][f'padding-{padding_left}'] = f"{padding_left}px"
            
            # Recursively parse children
            children = node.get('children', [])
            for child in children:
                self._parse_node_properties(child, tokens)
                
        except Exception as e:
            logger.error(f"Error parsing node properties: {e}")
    
    def generate_css_variables(self, tokens: Dict[str, Any]) -> str:
        """
        Generate CSS variables from design tokens
        
        Args:
            tokens: Design tokens object
            
        Returns:
            CSS variables string
        """
        css_lines = [':root {']
        
        # Colors
        for name, value in tokens.get('colors', {}).items():
            var_name = re.sub(r'\s+', '-', name.lower())
            css_lines.append(f'  --color-{var_name}: {value};')
        
        # Typography
        for name, style in tokens.get('typography', {}).items():
            var_name = re.sub(r'\s+', '-', name.lower())
            css_lines.append(f'  --font-{var_name}-family: {style.get("font_family", "Inter")};')
            css_lines.append(f'  --font-{var_name}-size: {style.get("font_size", "16px")};')
            css_lines.append(f'  --font-{var_name}-weight: {style.get("font_weight", "400")};')
            css_lines.append(f'  --font-{var_name}-line-height: {style.get("line_height", "normal")};')
        
        # Spacing
        for name, value in tokens.get('spacing', {}).items():
            css_lines.append(f'  --space-{name}: {value};')
        
        # Shadows
        for name, value in tokens.get('shadows', {}).items():
            var_name = re.sub(r'\s+', '-', name.lower())
            css_lines.append(f'  --shadow-{var_name}: {value};')
        
        # Border Radius
        for name, value in tokens.get('border_radius', {}).items():
            css_lines.append(f'  --{name}: {value};')
        
        css_lines.append('}')
        return '\n'.join(css_lines)
    
    def handle_api_error(self, error_message: str, status_code: int = None) -> FigmaIntegrationError:
        """
        Handle and classify Figma API errors
        
        Args:
            error_message: Error message from API
            status_code: HTTP status code
            
        Returns:
            Appropriate exception instance
        """
        if status_code == 401 or 'unauthorized' in error_message.lower():
            return FigmaAuthError(f"Authentication failed: {error_message}")
        elif status_code == 403 or 'forbidden' in error_message.lower():
            return FigmaAuthError(f"Access denied: {error_message}")
        elif status_code == 404 or 'not found' in error_message.lower():
            return FigmaNotFoundError(f"File or node not found: {error_message}")
        elif status_code == 429 or 'rate limit' in error_message.lower():
            return FigmaRateLimitError(f"Rate limit exceeded: {error_message}")
        elif 'network' in error_message.lower() or 'timeout' in error_message.lower():
            return FigmaNetworkError(f"Network error: {error_message}")
        else:
            return FigmaIntegrationError(f"Unknown error: {error_message}")
    
    def log_operation(self, operation: str, params: Dict, result: Dict):
        """
        Log API operation for debugging and monitoring
        
        Args:
            operation: Operation name
            params: Operation parameters
            result: Operation result
        """
        log_entry = {
            'operation': operation,
            'params': params,
            'success': 'error' not in result,
            'error': result.get('error'),
            'timestamp': None  # Will be set by logger
        }
        
        if log_entry['success']:
            logger.info(f"Figma API operation successful: {operation}", extra=log_entry)
        else:
            logger.error(f"Figma API operation failed: {operation}", extra=log_entry)


# Utility functions for common operations
def extract_figma_info(figma_url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract both file key and node ID from Figma URL
    
    Args:
        figma_url: Full Figma URL
        
    Returns:
        Tuple of (file_key, node_id)
    """
    integration = FigmaIntegration()
    file_key = integration.extract_file_key(figma_url)
    node_id = integration.extract_node_id(figma_url)
    return file_key, node_id


def validate_figma_params(file_key: str, node_id: str = None) -> bool:
    """
    Validate Figma parameters
    
    Args:
        file_key: Figma file key
        node_id: Optional node ID
        
    Returns:
        True if valid
    """
    integration = FigmaIntegration()
    
    if not integration.is_valid_file_key(file_key):
        return False
    
    if node_id and not integration.is_valid_node_id(node_id):
        return False
    
    return True


def create_asset_directory(base_path: str, asset_type: str) -> Path:
    """
    Create directory for Figma assets
    
    Args:
        base_path: Base directory path
        asset_type: Type of assets (images, icons, etc.)
        
    Returns:
        Path object for the created directory
    """
    asset_dir = Path(base_path) / 'figma-assets' / asset_type
    asset_dir.mkdir(parents=True, exist_ok=True)
    return asset_dir