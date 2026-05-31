"""
Figma Asset Extraction Service
Integrates with MCP Figma tools to provide comprehensive asset extraction capabilities
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from dataclasses import asdict

from .figma_asset_extractor import (
    FigmaAssetExtractor, AssetMetadata, AssetType, ExportFormat,
    BatchExtractionConfig
)

logger = logging.getLogger(__name__)


class FigmaAssetService:
    """
    Service class that integrates FigmaAssetExtractor with MCP Figma tools
    """
    
    def __init__(self, base_output_dir: str = "static/figma-assets"):
        self.extractor = FigmaAssetExtractor(base_output_dir)
        self.base_output_dir = Path(base_output_dir)
        
    def extract_assets_from_figma(
        self,
        file_key: str,
        node_id: str = None,
        asset_types: List[str] = None,
        output_directory: str = None
    ) -> Dict[str, Any]:
        """
        Extract assets from Figma using MCP tools
        
        Args:
            file_key: Figma file key
            node_id: Optional specific node ID
            asset_types: List of asset types to extract
            output_directory: Output directory (optional)
            
        Returns:
            Dictionary with extraction results
        """
        try:
            # Set defaults
            if asset_types is None:
                asset_types = ['icon', 'image', 'component']
            
            if output_directory is None:
                output_directory = str(self.base_output_dir)
            
            # Get Figma data using MCP tools
            figma_data = self._get_figma_data_mcp(file_key, node_id)
            if not figma_data:
                return {
                    'success': False,
                    'error': 'Failed to fetch Figma data',
                    'assets': []
                }
            
            # Find extractable nodes
            extractable_nodes = self._find_extractable_nodes_in_data(
                figma_data, asset_types
            )
            
            # Prepare nodes for download
            download_nodes = self._prepare_download_nodes(
                extractable_nodes, output_directory
            )
            
            # Download assets using MCP tools
            download_result = self._download_assets_mcp(
                file_key, download_nodes, output_directory
            )
            
            # Create asset metadata
            assets = self._create_asset_metadata_from_download(
                download_result, extractable_nodes, file_key
            )
            
            # Generate manifest
            manifest_path = Path(output_directory) / "asset_manifest.json"
            self.extractor.generate_asset_manifest(assets, str(manifest_path))
            
            return {
                'success': True,
                'total_assets': len(assets),
                'assets': [asdict(asset) for asset in assets],
                'manifest_path': str(manifest_path),
                'download_result': download_result
            }
            
        except Exception as e:
            logger.error(f"Error extracting assets from Figma: {e}")
            return {
                'success': False,
                'error': str(e),
                'assets': []
            }
    
    def extract_design_tokens(self, file_key: str) -> Dict[str, Any]:
        """
        Extract design tokens from Figma file
        
        Args:
            file_key: Figma file key
            
        Returns:
            Dictionary with design tokens
        """
        try:
            # Get Figma data
            figma_data = self._get_figma_data_mcp(file_key)
            if not figma_data:
                return {
                    'success': False,
                    'error': 'Failed to fetch Figma data',
                    'tokens': {}
                }
            
            # Parse design tokens
            tokens = self.extractor.figma_integration.parse_design_tokens(figma_data)
            
            # Generate CSS variables
            css_variables = self.extractor.figma_integration.generate_css_variables(tokens)
            
            # Save tokens to file
            tokens_path = self.base_output_dir / "design-tokens.json"
            css_path = self.base_output_dir / "design-tokens.css"
            
            self.base_output_dir.mkdir(parents=True, exist_ok=True)
            
            with open(tokens_path, 'w') as f:
                json.dump(tokens, f, indent=2)
            
            with open(css_path, 'w') as f:
                f.write(css_variables)
            
            return {
                'success': True,
                'tokens': tokens,
                'css_variables': css_variables,
                'tokens_path': str(tokens_path),
                'css_path': str(css_path)
            }
            
        except Exception as e:
            logger.error(f"Error extracting design tokens: {e}")
            return {
                'success': False,
                'error': str(e),
                'tokens': {}
            }
    
    def batch_extract_assets(
        self,
        file_key: str,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Perform batch asset extraction
        
        Args:
            file_key: Figma file key
            config: Batch extraction configuration
            
        Returns:
            Batch extraction results
        """
        try:
            # Create batch config
            batch_config = BatchExtractionConfig(
                file_key=file_key,
                output_directory=config.get('output_directory', str(self.base_output_dir)),
                asset_types=[AssetType(t) for t in config.get('asset_types', ['icon', 'image'])],
                export_formats=[ExportFormat(f) for f in config.get('export_formats', ['svg', 'png'])],
                export_scales=config.get('export_scales', [1.0, 2.0]),
                naming_convention=config.get('naming_convention', 'descriptive'),
                organize_by_type=config.get('organize_by_type', True),
                include_metadata=config.get('include_metadata', True),
                overwrite_existing=config.get('overwrite_existing', False)
            )
            
            # Extract assets
            extracted_assets = self.extractor.extract_batch_assets(batch_config)
            
            # Validate extraction
            validation_report = self.extractor.validate_extracted_assets(extracted_assets)
            
            return {
                'success': True,
                'config': asdict(batch_config),
                'extracted_assets': [asdict(asset) for asset in extracted_assets],
                'validation_report': validation_report,
                'total_extracted': len(extracted_assets)
            }
            
        except Exception as e:
            logger.error(f"Error in batch extraction: {e}")
            return {
                'success': False,
                'error': str(e),
                'extracted_assets': []
            }
    
    def organize_extracted_assets(
        self,
        assets: List[Dict],
        organization_scheme: str = "type"
    ) -> Dict[str, List[Dict]]:
        """
        Organize extracted assets by various schemes
        
        Args:
            assets: List of asset dictionaries
            organization_scheme: Organization scheme
            
        Returns:
            Organized assets
        """
        # Convert dicts to AssetMetadata objects
        asset_objects = []
        for asset_dict in assets:
            # Create AssetMetadata from dict
            metadata = AssetMetadata(
                node_id=asset_dict['node_id'],
                name=asset_dict['name'],
                asset_type=AssetType(asset_dict['asset_type']),
                export_format=ExportFormat(asset_dict['export_format']),
                file_name=asset_dict['file_name'],
                local_path=asset_dict['local_path'],
                figma_url=asset_dict['figma_url'],
                dimensions=asset_dict['dimensions'],
                properties=asset_dict['properties'],
                extracted_at=asset_dict['extracted_at']
            )
            asset_objects.append(metadata)
        
        # Organize assets
        organized = self.extractor.organize_assets(asset_objects, organization_scheme)
        
        # Convert back to dicts
        result = {}
        for key, asset_list in organized.items():
            result[key] = [asdict(asset) for asset in asset_list]
        
        return result
    
    def get_asset_inventory(self, directory: str = None) -> Dict[str, Any]:
        """
        Get inventory of assets in directory
        
        Args:
            directory: Directory to scan (optional)
            
        Returns:
            Asset inventory
        """
        if directory is None:
            directory = str(self.base_output_dir)
        
        directory_path = Path(directory)
        
        if not directory_path.exists():
            return {
                'success': False,
                'error': 'Directory does not exist',
                'inventory': {}
            }
        
        inventory = {
            'directory': str(directory_path),
            'scanned_at': self._get_current_timestamp(),
            'total_files': 0,
            'files_by_type': {},
            'files_by_format': {},
            'total_size_bytes': 0,
            'files': []
        }
        
        try:
            # Scan directory recursively
            for file_path in directory_path.rglob('*'):
                if file_path.is_file():
                    file_info = self._get_file_info(file_path)
                    inventory['files'].append(file_info)
                    inventory['total_files'] += 1
                    inventory['total_size_bytes'] += file_info['size_bytes']
                    
                    # Count by extension
                    ext = file_info['extension']
                    inventory['files_by_format'][ext] = inventory['files_by_format'].get(ext, 0) + 1
                    
                    # Count by inferred type
                    asset_type = self._infer_asset_type(file_path)
                    inventory['files_by_type'][asset_type] = inventory['files_by_type'].get(asset_type, 0) + 1
            
            return {
                'success': True,
                'inventory': inventory
            }
            
        except Exception as e:
            logger.error(f"Error scanning asset inventory: {e}")
            return {
                'success': False,
                'error': str(e),
                'inventory': {}
            }
    
    # Private helper methods for MCP integration
    
    def _get_figma_data_mcp(self, file_key: str, node_id: str = None) -> Optional[Dict]:
        """Get Figma data using MCP tools (placeholder for actual MCP integration)"""
        # This would use the actual MCP figma tools in practice
        # For now, return a mock structure for testing
        return {
            'document': {
                'id': '0:0',
                'name': 'Document',
                'type': 'DOCUMENT',
                'children': [
                    {
                        'id': '1:1',
                        'name': 'Sample Icon',
                        'type': 'VECTOR',
                        'absoluteBoundingBox': {'x': 0, 'y': 0, 'width': 24, 'height': 24}
                    },
                    {
                        'id': '1:2',
                        'name': 'Sample Image',
                        'type': 'RECTANGLE',
                        'absoluteBoundingBox': {'x': 0, 'y': 0, 'width': 200, 'height': 150},
                        'fills': [{'type': 'IMAGE', 'imageRef': 'sample_image_ref'}]
                    }
                ]
            }
        }
    
    def _find_extractable_nodes_in_data(
        self,
        figma_data: Dict,
        asset_types: List[str]
    ) -> List[Dict]:
        """Find extractable nodes in Figma data"""
        extractable = []
        
        def traverse_node(node):
            # Check if node is extractable
            node_type = node.get('type', '')
            
            # Map asset types to node types
            type_mapping = {
                'icon': ['VECTOR', 'BOOLEAN_OPERATION'],
                'image': ['RECTANGLE', 'ELLIPSE', 'FRAME'],
                'component': ['COMPONENT', 'COMPONENT_SET'],
                'svg': ['VECTOR', 'BOOLEAN_OPERATION', 'FRAME']
            }
            
            for asset_type in asset_types:
                if node_type in type_mapping.get(asset_type, []):
                    extractable.append({
                        'node': node,
                        'asset_type': asset_type
                    })
                    break
            
            # Traverse children
            for child in node.get('children', []):
                traverse_node(child)
        
        if figma_data.get('document'):
            traverse_node(figma_data['document'])
        
        return extractable
    
    def _prepare_download_nodes(
        self,
        extractable_nodes: List[Dict],
        output_directory: str
    ) -> List[Dict]:
        """Prepare nodes for MCP download"""
        download_nodes = []
        
        for item in extractable_nodes:
            node = item['node']
            asset_type = item['asset_type']
            
            # Determine export format
            export_format = 'svg' if asset_type in ['icon', 'svg'] else 'png'
            
            # Generate filename
            filename = self.extractor._generate_asset_filename(
                node, export_format
            )
            
            # Check for image/gif references
            image_ref = self._get_image_ref_from_node(node)
            gif_ref = self._get_gif_ref_from_node(node)
            
            download_node = {
                'nodeId': node['id'],
                'fileName': filename,
                'imageRef': image_ref,
                'gifRef': gif_ref,
                'needsCropping': False,
                'requiresImageDimensions': asset_type in ['image', 'component']
            }
            
            download_nodes.append(download_node)
        
        return download_nodes
    
    def _download_assets_mcp(
        self,
        file_key: str,
        download_nodes: List[Dict],
        output_directory: str
    ) -> Dict[str, Any]:
        """Download assets using MCP tools (placeholder)"""
        # This would use the actual MCP download_figma_images tool
        # For now, create placeholder files
        
        downloaded = []
        errors = []
        
        output_path = Path(output_directory)
        output_path.mkdir(parents=True, exist_ok=True)
        
        for node in download_nodes:
            try:
                file_path = output_path / node['fileName']
                
                # Create placeholder file
                with open(file_path, 'w') as f:
                    f.write(f"Placeholder for {node['fileName']}")
                
                downloaded.append({
                    'nodeId': node['nodeId'],
                    'fileName': node['fileName'],
                    'localPath': str(file_path),
                    'success': True
                })
                
            except Exception as e:
                errors.append({
                    'nodeId': node['nodeId'],
                    'fileName': node['fileName'],
                    'error': str(e)
                })
        
        return {
            'downloaded': downloaded,
            'errors': errors,
            'total_requested': len(download_nodes),
            'total_downloaded': len(downloaded),
            'total_errors': len(errors)
        }
    
    def _create_asset_metadata_from_download(
        self,
        download_result: Dict,
        extractable_nodes: List[Dict],
        file_key: str
    ) -> List[AssetMetadata]:
        """Create asset metadata from download results"""
        assets = []
        
        # Create lookup for nodes by ID
        nodes_by_id = {}
        for item in extractable_nodes:
            nodes_by_id[item['node']['id']] = item
        
        for downloaded in download_result['downloaded']:
            node_id = downloaded['nodeId']
            
            if node_id in nodes_by_id:
                node_item = nodes_by_id[node_id]
                node = node_item['node']
                asset_type = node_item['asset_type']
                
                # Determine export format from filename
                extension = Path(downloaded['fileName']).suffix.lstrip('.')
                export_format = ExportFormat(extension)
                
                # Create metadata
                metadata = AssetMetadata(
                    node_id=node_id,
                    name=node.get('name', 'Unnamed'),
                    asset_type=AssetType(asset_type),
                    export_format=export_format,
                    file_name=downloaded['fileName'],
                    local_path=downloaded['localPath'],
                    figma_url=f"https://figma.com/file/{file_key}?node-id={node_id}",
                    dimensions=self.extractor._extract_dimensions(node),
                    properties=self.extractor._extract_asset_properties(node),
                    extracted_at=self._get_current_timestamp(),
                    image_ref=self._get_image_ref_from_node(node),
                    gif_ref=self._get_gif_ref_from_node(node)
                )
                
                assets.append(metadata)
        
        return assets
    
    def _get_image_ref_from_node(self, node: Dict) -> Optional[str]:
        """Extract image reference from node"""
        fills = node.get('fills', [])
        for fill in fills:
            if fill.get('type') == 'IMAGE':
                return fill.get('imageRef')
        return None
    
    def _get_gif_ref_from_node(self, node: Dict) -> Optional[str]:
        """Extract GIF reference from node"""
        fills = node.get('fills', [])
        for fill in fills:
            if fill.get('type') == 'IMAGE' and fill.get('gifRef'):
                return fill.get('gifRef')
        return None
    
    def _get_file_info(self, file_path: Path) -> Dict[str, Any]:
        """Get file information"""
        stat = file_path.stat()
        return {
            'name': file_path.name,
            'path': str(file_path),
            'extension': file_path.suffix.lstrip('.'),
            'size_bytes': stat.st_size,
            'modified_at': stat.st_mtime,
            'created_at': stat.st_ctime
        }
    
    def _infer_asset_type(self, file_path: Path) -> str:
        """Infer asset type from file path and extension"""
        extension = file_path.suffix.lstrip('.').lower()
        
        if extension == 'svg':
            return 'svg'
        elif extension in ['png', 'jpg', 'jpeg']:
            # Check if it's in icons directory
            if 'icon' in str(file_path).lower():
                return 'icon'
            else:
                return 'image'
        elif extension == 'gif':
            return 'gif'
        else:
            return 'unknown'
    
    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format"""
        from datetime import datetime
        return datetime.now().isoformat()


# Utility functions for service integration

def create_asset_service(base_output_dir: str = "static/figma-assets") -> FigmaAssetService:
    """Create a new asset service instance"""
    return FigmaAssetService(base_output_dir)


def extract_figma_assets(
    file_key: str,
    asset_types: List[str] = None,
    output_directory: str = None
) -> Dict[str, Any]:
    """Quick asset extraction from Figma"""
    service = FigmaAssetService()
    return service.extract_assets_from_figma(
        file_key, asset_types=asset_types, output_directory=output_directory
    )


def extract_figma_design_tokens(file_key: str) -> Dict[str, Any]:
    """Quick design token extraction from Figma"""
    service = FigmaAssetService()
    return service.extract_design_tokens(file_key)


def get_figma_asset_inventory(directory: str = None) -> Dict[str, Any]:
    """Quick asset inventory scan"""
    service = FigmaAssetService()
    return service.get_asset_inventory(directory)