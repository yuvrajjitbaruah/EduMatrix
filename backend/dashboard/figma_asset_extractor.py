"""
Figma Asset Extraction Utilities for EduMatrix Platform
Provides comprehensive utilities for extracting various types of assets from Figma files
"""

import os
import json
import logging
from typing import Dict, List, Optional, Tuple, Any, Union
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum
import re
from datetime import datetime

from .figma_integration import FigmaIntegration, FigmaIntegrationError

logger = logging.getLogger(__name__)


class AssetType(Enum):
    """Enumeration of supported asset types"""
    IMAGE = "image"
    ICON = "icon"
    SVG = "svg"
    GIF = "gif"
    COMPONENT = "component"
    FRAME = "frame"


class ExportFormat(Enum):
    """Enumeration of supported export formats"""
    SVG = "svg"
    PNG = "png"
    JPG = "jpg"
    GIF = "gif"


@dataclass
class AssetMetadata:
    """Metadata for extracted assets"""
    node_id: str
    name: str
    asset_type: AssetType
    export_format: ExportFormat
    file_name: str
    local_path: str
    figma_url: str
    dimensions: Dict[str, float]
    properties: Dict[str, Any]
    extracted_at: str
    image_ref: Optional[str] = None
    gif_ref: Optional[str] = None
    crop_transform: Optional[List[List[float]]] = None
    needs_cropping: bool = False
    requires_dimensions: bool = False


@dataclass
class BatchExtractionConfig:
    """Configuration for batch asset extraction"""
    file_key: str
    output_directory: str
    asset_types: List[AssetType]
    export_formats: List[ExportFormat]
    export_scales: List[float]
    naming_convention: str = "descriptive"  # "descriptive", "node_id", "custom"
    organize_by_type: bool = True
    include_metadata: bool = True
    overwrite_existing: bool = False


class FigmaAssetExtractor:
    """
    Comprehensive asset extraction utility for Figma files
    """
    
    def __init__(self, base_output_dir: str = "static/figma-assets"):
        self.base_output_dir = Path(base_output_dir)
        self.figma_integration = FigmaIntegration()
        self.extracted_assets: List[AssetMetadata] = []
        
        # Default export scales for different asset types
        self.default_scales = {
            AssetType.ICON: [1.0, 2.0],
            AssetType.IMAGE: [1.0, 2.0, 3.0],
            AssetType.SVG: [1.0],
            AssetType.GIF: [1.0]
        }
        
        # Supported node types for each asset type
        self.supported_node_types = {
            AssetType.IMAGE: ["RECTANGLE", "ELLIPSE", "FRAME", "GROUP"],
            AssetType.ICON: ["VECTOR", "BOOLEAN_OPERATION", "FRAME", "GROUP"],
            AssetType.SVG: ["VECTOR", "BOOLEAN_OPERATION", "FRAME", "GROUP"],
            AssetType.COMPONENT: ["COMPONENT", "COMPONENT_SET"],
            AssetType.FRAME: ["FRAME"]
        }
    
    def extract_single_asset(
        self,
        file_key: str,
        node_id: str,
        asset_type: AssetType,
        export_format: ExportFormat,
        output_path: str,
        scale: float = 1.0,
        custom_name: Optional[str] = None
    ) -> Optional[AssetMetadata]:
        """
        Extract a single asset from Figma
        
        Args:
            file_key: Figma file key
            node_id: Node ID to extract
            asset_type: Type of asset
            export_format: Export format
            output_path: Local output path
            scale: Export scale (for raster formats)
            custom_name: Custom filename (optional)
            
        Returns:
            AssetMetadata if successful, None otherwise
        """
        try:
            # Validate inputs
            if not self.figma_integration.is_valid_file_key(file_key):
                raise ValueError(f"Invalid file key: {file_key}")
            
            if not self.figma_integration.is_valid_node_id(node_id):
                raise ValueError(f"Invalid node ID: {node_id}")
            
            # Get node data from Figma (this would use MCP tools in practice)
            node_data = self._get_node_data(file_key, node_id)
            if not node_data:
                logger.error(f"Could not fetch node data for {node_id}")
                return None
            
            # Validate node type for asset type
            if not self._is_valid_node_for_asset_type(node_data, asset_type):
                logger.warning(f"Node {node_id} type not suitable for {asset_type.value}")
                return None
            
            # Generate filename
            filename = custom_name or self._generate_asset_filename(
                node_data, export_format.value, scale
            )
            
            # Create output directory
            output_dir = Path(output_path)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Extract asset properties
            properties = self._extract_asset_properties(node_data)
            dimensions = self._extract_dimensions(node_data)
            
            # Create metadata
            metadata = AssetMetadata(
                node_id=node_id,
                name=node_data.get('name', 'Unnamed'),
                asset_type=asset_type,
                export_format=export_format,
                file_name=filename,
                local_path=str(output_dir / filename),
                figma_url=f"https://figma.com/file/{file_key}?node-id={node_id}",
                dimensions=dimensions,
                properties=properties,
                extracted_at=datetime.now().isoformat(),
                image_ref=self._get_image_ref(node_data),
                gif_ref=self._get_gif_ref(node_data),
                crop_transform=self._get_crop_transform(node_data),
                needs_cropping=self._needs_cropping(node_data),
                requires_dimensions=self._requires_dimensions(asset_type)
            )
            
            # Download asset (this would use MCP tools in practice)
            success = self._download_asset(file_key, metadata, scale)
            
            if success:
                self.extracted_assets.append(metadata)
                logger.info(f"Successfully extracted asset: {filename}")
                return metadata
            else:
                logger.error(f"Failed to download asset: {filename}")
                return None
                
        except Exception as e:
            logger.error(f"Error extracting asset {node_id}: {e}")
            return None
    
    def extract_batch_assets(
        self,
        config: BatchExtractionConfig
    ) -> List[AssetMetadata]:
        """
        Extract multiple assets in batch
        
        Args:
            config: Batch extraction configuration
            
        Returns:
            List of successfully extracted asset metadata
        """
        extracted = []
        
        try:
            # Get all nodes from Figma file
            file_data = self._get_file_data(config.file_key)
            if not file_data:
                logger.error(f"Could not fetch file data for {config.file_key}")
                return extracted
            
            # Find extractable nodes
            extractable_nodes = self._find_extractable_nodes(
                file_data, config.asset_types
            )
            
            logger.info(f"Found {len(extractable_nodes)} extractable nodes")
            
            # Extract each asset
            for node_data in extractable_nodes:
                for asset_type in config.asset_types:
                    if not self._is_valid_node_for_asset_type(node_data, asset_type):
                        continue
                    
                    for export_format in config.export_formats:
                        # Skip incompatible format/type combinations
                        if not self._is_compatible_format_type(export_format, asset_type):
                            continue
                        
                        for scale in config.export_scales:
                            # Determine output path
                            output_path = self._get_batch_output_path(
                                config, asset_type, export_format
                            )
                            
                            # Extract asset
                            metadata = self.extract_single_asset(
                                config.file_key,
                                node_data['id'],
                                asset_type,
                                export_format,
                                output_path,
                                scale
                            )
                            
                            if metadata:
                                extracted.append(metadata)
            
            # Save batch metadata
            if config.include_metadata:
                self._save_batch_metadata(config, extracted)
            
            logger.info(f"Batch extraction completed: {len(extracted)} assets extracted")
            
        except Exception as e:
            logger.error(f"Error in batch extraction: {e}")
        
        return extracted
    
    def extract_assets_by_type(
        self,
        file_key: str,
        asset_type: AssetType,
        output_directory: str,
        export_format: ExportFormat = None,
        scales: List[float] = None
    ) -> List[AssetMetadata]:
        """
        Extract all assets of a specific type from a Figma file
        
        Args:
            file_key: Figma file key
            asset_type: Type of assets to extract
            output_directory: Output directory
            export_format: Export format (defaults based on asset type)
            scales: Export scales (defaults based on asset type)
            
        Returns:
            List of extracted asset metadata
        """
        # Set defaults based on asset type
        if export_format is None:
            export_format = self._get_default_format(asset_type)
        
        if scales is None:
            scales = self.default_scales.get(asset_type, [1.0])
        
        # Create batch config
        config = BatchExtractionConfig(
            file_key=file_key,
            output_directory=output_directory,
            asset_types=[asset_type],
            export_formats=[export_format],
            export_scales=scales,
            organize_by_type=True,
            include_metadata=True
        )
        
        return self.extract_batch_assets(config)
    
    def extract_icons(
        self,
        file_key: str,
        output_directory: str,
        scales: List[float] = None
    ) -> List[AssetMetadata]:
        """
        Extract all icons from a Figma file as SVG
        
        Args:
            file_key: Figma file key
            output_directory: Output directory for icons
            scales: Export scales (default: [1.0])
            
        Returns:
            List of extracted icon metadata
        """
        return self.extract_assets_by_type(
            file_key,
            AssetType.ICON,
            output_directory,
            ExportFormat.SVG,
            scales or [1.0]
        )
    
    def extract_images(
        self,
        file_key: str,
        output_directory: str,
        format: ExportFormat = ExportFormat.PNG,
        scales: List[float] = None
    ) -> List[AssetMetadata]:
        """
        Extract all images from a Figma file
        
        Args:
            file_key: Figma file key
            output_directory: Output directory for images
            format: Export format (PNG or JPG)
            scales: Export scales (default: [1.0, 2.0])
            
        Returns:
            List of extracted image metadata
        """
        return self.extract_assets_by_type(
            file_key,
            AssetType.IMAGE,
            output_directory,
            format,
            scales or [1.0, 2.0]
        )
    
    def extract_components(
        self,
        file_key: str,
        output_directory: str,
        export_format: ExportFormat = ExportFormat.SVG
    ) -> List[AssetMetadata]:
        """
        Extract all components from a Figma file
        
        Args:
            file_key: Figma file key
            output_directory: Output directory for components
            export_format: Export format
            
        Returns:
            List of extracted component metadata
        """
        return self.extract_assets_by_type(
            file_key,
            AssetType.COMPONENT,
            output_directory,
            export_format,
            [1.0]
        )
    
    def organize_assets(
        self,
        assets: List[AssetMetadata],
        organization_scheme: str = "type"
    ) -> Dict[str, List[AssetMetadata]]:
        """
        Organize extracted assets by various schemes
        
        Args:
            assets: List of asset metadata
            organization_scheme: "type", "format", "scale", "name"
            
        Returns:
            Dictionary of organized assets
        """
        organized = {}
        
        for asset in assets:
            if organization_scheme == "type":
                key = asset.asset_type.value
            elif organization_scheme == "format":
                key = asset.export_format.value
            elif organization_scheme == "scale":
                # Extract scale from filename or properties
                key = f"scale_{self._extract_scale_from_asset(asset)}"
            elif organization_scheme == "name":
                # Group by base name (without scale/format suffixes)
                key = self._extract_base_name(asset.name)
            else:
                key = "all"
            
            if key not in organized:
                organized[key] = []
            organized[key].append(asset)
        
        return organized
    
    def generate_asset_manifest(
        self,
        assets: List[AssetMetadata],
        output_path: str
    ) -> bool:
        """
        Generate a manifest file for extracted assets
        
        Args:
            assets: List of asset metadata
            output_path: Path for manifest file
            
        Returns:
            True if successful
        """
        try:
            manifest = {
                "generated_at": datetime.now().isoformat(),
                "total_assets": len(assets),
                "assets_by_type": {},
                "assets": []
            }
            
            # Count by type
            for asset in assets:
                asset_type = asset.asset_type.value
                if asset_type not in manifest["assets_by_type"]:
                    manifest["assets_by_type"][asset_type] = 0
                manifest["assets_by_type"][asset_type] += 1
            
            # Add asset details
            for asset in assets:
                manifest["assets"].append(self._to_json_safe(asdict(asset)))
            
            # Write manifest
            with open(output_path, 'w') as f:
                json.dump(manifest, f, indent=2)
            
            logger.info(f"Asset manifest generated: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error generating asset manifest: {e}")
            return False
    
    def validate_extracted_assets(
        self,
        assets: List[AssetMetadata]
    ) -> Dict[str, Any]:
        """
        Validate extracted assets for completeness and quality
        
        Args:
            assets: List of asset metadata to validate
            
        Returns:
            Validation report
        """
        report = {
            "total_assets": len(assets),
            "valid_assets": 0,
            "invalid_assets": 0,
            "missing_files": [],
            "invalid_dimensions": [],
            "errors": []
        }
        
        for asset in assets:
            try:
                # Check if file exists
                if not Path(asset.local_path).exists():
                    report["missing_files"].append(asset.file_name)
                    report["invalid_assets"] += 1
                    continue
                
                # Check file size
                file_size = Path(asset.local_path).stat().st_size
                if file_size == 0:
                    report["errors"].append(f"Empty file: {asset.file_name}")
                    report["invalid_assets"] += 1
                    continue
                
                # Check dimensions for raster formats
                if asset.export_format in [ExportFormat.PNG, ExportFormat.JPG]:
                    if not asset.dimensions or asset.dimensions.get('width', 0) <= 0:
                        report["invalid_dimensions"].append(asset.file_name)
                        report["invalid_assets"] += 1
                        continue
                
                report["valid_assets"] += 1
                
            except Exception as e:
                report["errors"].append(f"Error validating {asset.file_name}: {e}")
                report["invalid_assets"] += 1
        
        return report
    
    # Private helper methods

    def _to_json_safe(self, value: Any) -> Any:
        """Convert dataclass dictionaries containing enums into JSON-safe values."""
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, dict):
            return {key: self._to_json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._to_json_safe(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self._to_json_safe(item) for item in value)
        return value
    
    def _get_node_data(self, file_key: str, node_id: str) -> Optional[Dict]:
        """Get node data from Figma API (placeholder for MCP integration)"""
        # This would use the MCP figma tools in practice
        # For now, return a mock structure
        return {
            'id': node_id,
            'name': f'Node {node_id}',
            'type': 'FRAME',
            'absoluteBoundingBox': {'x': 0, 'y': 0, 'width': 100, 'height': 100},
            'fills': [],
            'effects': [],
            'cornerRadius': 0
        }
    
    def _get_file_data(self, file_key: str) -> Optional[Dict]:
        """Get complete file data from Figma API (placeholder for MCP integration)"""
        # This would use the MCP figma tools in practice
        return {
            'document': {
                'id': '0:0',
                'name': 'Document',
                'type': 'DOCUMENT',
                'children': []
            }
        }
    
    def _find_extractable_nodes(
        self,
        file_data: Dict,
        asset_types: List[AssetType]
    ) -> List[Dict]:
        """Find all nodes that can be extracted as assets"""
        extractable = []
        
        def traverse_node(node):
            # Check if node is extractable for any of the requested asset types
            for asset_type in asset_types:
                if self._is_valid_node_for_asset_type(node, asset_type):
                    extractable.append(node)
                    break
            
            # Traverse children
            for child in node.get('children', []):
                traverse_node(child)
        
        if file_data.get('document'):
            traverse_node(file_data['document'])
        
        return extractable
    
    def _is_valid_node_for_asset_type(self, node_data: Dict, asset_type: AssetType) -> bool:
        """Check if a node is valid for the specified asset type"""
        node_type = node_data.get('type', '')
        supported_types = self.supported_node_types.get(asset_type, [])
        return node_type in supported_types
    
    def _generate_asset_filename(
        self,
        node_data: Dict,
        extension: str,
        scale: float = 1.0
    ) -> str:
        """Generate filename for an asset"""
        name = node_data.get('name', 'asset')
        # Sanitize name
        sanitized = re.sub(r'[^a-z0-9]', '-', name.lower())
        sanitized = re.sub(r'-+', '-', sanitized).strip('-')
        
        # Add scale suffix for non-1x scales
        scale_suffix = f"@{scale}x" if scale != 1.0 else ""
        
        return f"{sanitized}{scale_suffix}.{extension}"
    
    def _extract_asset_properties(self, node_data: Dict) -> Dict[str, Any]:
        """Extract relevant properties from node data"""
        return {
            'type': node_data.get('type'),
            'visible': node_data.get('visible', True),
            'opacity': node_data.get('opacity', 1.0),
            'blendMode': node_data.get('blendMode'),
            'fills': node_data.get('fills', []),
            'strokes': node_data.get('strokes', []),
            'effects': node_data.get('effects', []),
            'cornerRadius': node_data.get('cornerRadius'),
            'constraints': node_data.get('constraints', {})
        }
    
    def _extract_dimensions(self, node_data: Dict) -> Dict[str, float]:
        """Extract dimensions from node data"""
        bbox = node_data.get('absoluteBoundingBox', {})
        return {
            'width': bbox.get('width', 0),
            'height': bbox.get('height', 0),
            'x': bbox.get('x', 0),
            'y': bbox.get('y', 0)
        }
    
    def _get_image_ref(self, node_data: Dict) -> Optional[str]:
        """Extract image reference from node fills"""
        fills = node_data.get('fills', [])
        for fill in fills:
            if fill.get('type') == 'IMAGE':
                return fill.get('imageRef')
        return None
    
    def _get_gif_ref(self, node_data: Dict) -> Optional[str]:
        """Extract GIF reference from node fills"""
        fills = node_data.get('fills', [])
        for fill in fills:
            if fill.get('type') == 'IMAGE' and fill.get('gifRef'):
                return fill.get('gifRef')
        return None
    
    def _get_crop_transform(self, node_data: Dict) -> Optional[List[List[float]]]:
        """Extract crop transform matrix from node"""
        fills = node_data.get('fills', [])
        for fill in fills:
            if fill.get('type') == 'IMAGE' and fill.get('imageTransform'):
                return fill.get('imageTransform')
        return None
    
    def _needs_cropping(self, node_data: Dict) -> bool:
        """Check if node needs cropping based on transform"""
        transform = self._get_crop_transform(node_data)
        if not transform:
            return False
        
        # Check if transform is not identity matrix
        identity = [[1, 0, 0], [0, 1, 0]]
        return transform != identity
    
    def _requires_dimensions(self, asset_type: AssetType) -> bool:
        """Check if asset type requires dimension information"""
        return asset_type in [AssetType.IMAGE, AssetType.COMPONENT]
    
    def _download_asset(
        self,
        file_key: str,
        metadata: AssetMetadata,
        scale: float
    ) -> bool:
        """Download asset from Figma (placeholder for MCP integration)"""
        # This would use the MCP download_figma_images tool in practice
        # For now, create a placeholder file
        try:
            Path(metadata.local_path).parent.mkdir(parents=True, exist_ok=True)
            with open(metadata.local_path, 'w') as f:
                f.write(f"Placeholder for {metadata.name}")
            return True
        except Exception as e:
            logger.error(f"Error creating placeholder file: {e}")
            return False
    
    def _get_default_format(self, asset_type: AssetType) -> ExportFormat:
        """Get default export format for asset type"""
        defaults = {
            AssetType.ICON: ExportFormat.SVG,
            AssetType.SVG: ExportFormat.SVG,
            AssetType.IMAGE: ExportFormat.PNG,
            AssetType.GIF: ExportFormat.GIF,
            AssetType.COMPONENT: ExportFormat.SVG,
            AssetType.FRAME: ExportFormat.PNG
        }
        return defaults.get(asset_type, ExportFormat.PNG)
    
    def _is_compatible_format_type(
        self,
        export_format: ExportFormat,
        asset_type: AssetType
    ) -> bool:
        """Check if export format is compatible with asset type"""
        compatible = {
            AssetType.ICON: [ExportFormat.SVG, ExportFormat.PNG],
            AssetType.SVG: [ExportFormat.SVG],
            AssetType.IMAGE: [ExportFormat.PNG, ExportFormat.JPG],
            AssetType.GIF: [ExportFormat.GIF, ExportFormat.PNG],
            AssetType.COMPONENT: [ExportFormat.SVG, ExportFormat.PNG],
            AssetType.FRAME: [ExportFormat.PNG, ExportFormat.JPG, ExportFormat.SVG]
        }
        return export_format in compatible.get(asset_type, [])
    
    def _get_batch_output_path(
        self,
        config: BatchExtractionConfig,
        asset_type: AssetType,
        export_format: ExportFormat
    ) -> str:
        """Get output path for batch extraction"""
        base_path = Path(config.output_directory)
        
        if config.organize_by_type:
            return str(base_path / asset_type.value / export_format.value)
        else:
            return str(base_path)
    
    def _save_batch_metadata(
        self,
        config: BatchExtractionConfig,
        extracted: List[AssetMetadata]
    ) -> None:
        """Save metadata for batch extraction"""
        metadata_path = Path(config.output_directory) / "extraction_metadata.json"
        
        metadata = {
            "extraction_config": self._to_json_safe(asdict(config)),
            "extracted_at": datetime.now().isoformat(),
            "total_extracted": len(extracted),
            "assets": [self._to_json_safe(asdict(asset)) for asset in extracted]
        }
        
        try:
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            logger.info(f"Batch metadata saved: {metadata_path}")
        except Exception as e:
            logger.error(f"Error saving batch metadata: {e}")
    
    def _extract_scale_from_asset(self, asset: AssetMetadata) -> str:
        """Extract scale information from asset"""
        # Look for scale in filename
        match = re.search(r'@(\d+(?:\.\d+)?)x', asset.file_name)
        if match:
            return match.group(1)
        return "1.0"
    
    def _extract_base_name(self, name: str) -> str:
        """Extract base name without scale/format suffixes"""
        # Remove scale suffix
        name = re.sub(r'@\d+(?:\.\d+)?x', '', name)
        # Remove extension
        name = re.sub(r'\.[^.]+$', '', name)
        return name


# Utility functions for common operations

def extract_all_icons(
    file_key: str,
    output_directory: str = "static/icons"
) -> List[AssetMetadata]:
    """
    Extract all icons from a Figma file
    
    Args:
        file_key: Figma file key
        output_directory: Output directory for icons
        
    Returns:
        List of extracted icon metadata
    """
    extractor = FigmaAssetExtractor()
    return extractor.extract_icons(file_key, output_directory)


def extract_all_images(
    file_key: str,
    output_directory: str = "static/images",
    scales: List[float] = None
) -> List[AssetMetadata]:
    """
    Extract all images from a Figma file
    
    Args:
        file_key: Figma file key
        output_directory: Output directory for images
        scales: Export scales (default: [1.0, 2.0])
        
    Returns:
        List of extracted image metadata
    """
    extractor = FigmaAssetExtractor()
    return extractor.extract_images(
        file_key,
        output_directory,
        ExportFormat.PNG,
        scales or [1.0, 2.0]
    )


def extract_design_system_assets(
    file_key: str,
    output_directory: str = "static/design-system"
) -> Dict[str, List[AssetMetadata]]:
    """
    Extract all design system assets (icons, components, images)
    
    Args:
        file_key: Figma file key
        output_directory: Base output directory
        
    Returns:
        Dictionary of extracted assets by type
    """
    extractor = FigmaAssetExtractor()
    
    # Create batch config for comprehensive extraction
    config = BatchExtractionConfig(
        file_key=file_key,
        output_directory=output_directory,
        asset_types=[AssetType.ICON, AssetType.IMAGE, AssetType.COMPONENT],
        export_formats=[ExportFormat.SVG, ExportFormat.PNG],
        export_scales=[1.0, 2.0],
        organize_by_type=True,
        include_metadata=True
    )
    
    extracted = extractor.extract_batch_assets(config)
    return extractor.organize_assets(extracted, "type")


def create_asset_inventory(
    assets: List[AssetMetadata],
    output_path: str = "static/asset_inventory.json"
) -> bool:
    """
    Create a comprehensive inventory of extracted assets
    
    Args:
        assets: List of asset metadata
        output_path: Path for inventory file
        
    Returns:
        True if successful
    """
    extractor = FigmaAssetExtractor()
    return extractor.generate_asset_manifest(assets, output_path)


def validate_asset_extraction(
    assets: List[AssetMetadata]
) -> Dict[str, Any]:
    """
    Validate extracted assets for completeness and quality
    
    Args:
        assets: List of asset metadata to validate
        
    Returns:
        Validation report
    """
    extractor = FigmaAssetExtractor()
    return extractor.validate_extracted_assets(assets)
