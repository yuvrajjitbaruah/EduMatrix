"""
Unit tests for Figma asset extraction utilities
"""

import json
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from django.test import TestCase

from .figma_asset_extractor import (
    FigmaAssetExtractor, AssetMetadata, AssetType, ExportFormat,
    BatchExtractionConfig
)
from .figma_asset_service import FigmaAssetService


TEST_TEMP_ROOT = Path(__file__).resolve().parents[2] / '.codex-temp' / 'figma-tests'


def _workspace_temp_dir():
    TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    temp_dir = TEST_TEMP_ROOT / f"run-{uuid.uuid4().hex}"
    temp_dir.mkdir(parents=True, exist_ok=False)
    return str(temp_dir)


class TestFigmaAssetExtractor(TestCase):
    """Test cases for FigmaAssetExtractor"""
    
    def setUp(self):
        self.temp_dir = _workspace_temp_dir()
        self.extractor = FigmaAssetExtractor(self.temp_dir)
    
    def tearDown(self):
        # Clean up temp directory
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_generate_asset_filename(self):
        """Test asset filename generation"""
        node_data = {
            'name': 'My Test Icon',
            'id': '1:123'
        }
        
        filename = self.extractor._generate_asset_filename(node_data, 'svg')
        self.assertEqual(filename, 'my-test-icon.svg')
        
        # Test with scale
        filename_scaled = self.extractor._generate_asset_filename(node_data, 'png', 2.0)
        self.assertEqual(filename_scaled, 'my-test-icon@2.0x.png')
    
    def test_extract_asset_properties(self):
        """Test asset property extraction"""
        node_data = {
            'type': 'VECTOR',
            'visible': True,
            'opacity': 0.8,
            'fills': [{'type': 'SOLID', 'color': {'r': 1, 'g': 0, 'b': 0}}],
            'cornerRadius': 8
        }
        
        properties = self.extractor._extract_asset_properties(node_data)
        
        self.assertEqual(properties['type'], 'VECTOR')
        self.assertEqual(properties['opacity'], 0.8)
        self.assertEqual(properties['cornerRadius'], 8)
        self.assertTrue(properties['visible'])
    
    def test_extract_dimensions(self):
        """Test dimension extraction"""
        node_data = {
            'absoluteBoundingBox': {
                'x': 10,
                'y': 20,
                'width': 100,
                'height': 50
            }
        }
        
        dimensions = self.extractor._extract_dimensions(node_data)
        
        self.assertEqual(dimensions['width'], 100)
        self.assertEqual(dimensions['height'], 50)
        self.assertEqual(dimensions['x'], 10)
        self.assertEqual(dimensions['y'], 20)
    
    def test_is_valid_node_for_asset_type(self):
        """Test node type validation for asset types"""
        vector_node = {'type': 'VECTOR'}
        frame_node = {'type': 'FRAME'}
        component_node = {'type': 'COMPONENT'}
        
        # Test icon asset type
        self.assertTrue(
            self.extractor._is_valid_node_for_asset_type(vector_node, AssetType.ICON)
        )
        self.assertFalse(
            self.extractor._is_valid_node_for_asset_type(component_node, AssetType.ICON)
        )
        
        # Test component asset type
        self.assertTrue(
            self.extractor._is_valid_node_for_asset_type(component_node, AssetType.COMPONENT)
        )
        self.assertFalse(
            self.extractor._is_valid_node_for_asset_type(vector_node, AssetType.COMPONENT)
        )
    
    def test_get_default_format(self):
        """Test default format selection"""
        self.assertEqual(
            self.extractor._get_default_format(AssetType.ICON),
            ExportFormat.SVG
        )
        self.assertEqual(
            self.extractor._get_default_format(AssetType.IMAGE),
            ExportFormat.PNG
        )
    
    def test_is_compatible_format_type(self):
        """Test format/type compatibility"""
        # SVG format should be compatible with icons
        self.assertTrue(
            self.extractor._is_compatible_format_type(ExportFormat.SVG, AssetType.ICON)
        )
        
        # JPG format should not be compatible with icons
        self.assertFalse(
            self.extractor._is_compatible_format_type(ExportFormat.JPG, AssetType.ICON)
        )
        
        # PNG format should be compatible with images
        self.assertTrue(
            self.extractor._is_compatible_format_type(ExportFormat.PNG, AssetType.IMAGE)
        )
    
    def test_organize_assets(self):
        """Test asset organization"""
        assets = [
            AssetMetadata(
                node_id='1:1',
                name='Icon 1',
                asset_type=AssetType.ICON,
                export_format=ExportFormat.SVG,
                file_name='icon1.svg',
                local_path='/path/icon1.svg',
                figma_url='https://figma.com/file/test',
                dimensions={},
                properties={},
                extracted_at='2024-01-01T00:00:00'
            ),
            AssetMetadata(
                node_id='1:2',
                name='Image 1',
                asset_type=AssetType.IMAGE,
                export_format=ExportFormat.PNG,
                file_name='image1.png',
                local_path='/path/image1.png',
                figma_url='https://figma.com/file/test',
                dimensions={},
                properties={},
                extracted_at='2024-01-01T00:00:00'
            )
        ]
        
        organized = self.extractor.organize_assets(assets, 'type')
        
        self.assertIn('icon', organized)
        self.assertIn('image', organized)
        self.assertEqual(len(organized['icon']), 1)
        self.assertEqual(len(organized['image']), 1)
    
    def test_generate_asset_manifest(self):
        """Test asset manifest generation"""
        assets = [
            AssetMetadata(
                node_id='1:1',
                name='Test Asset',
                asset_type=AssetType.ICON,
                export_format=ExportFormat.SVG,
                file_name='test.svg',
                local_path='/path/test.svg',
                figma_url='https://figma.com/file/test',
                dimensions={},
                properties={},
                extracted_at='2024-01-01T00:00:00'
            )
        ]
        
        manifest_path = Path(self.temp_dir) / 'manifest.json'
        success = self.extractor.generate_asset_manifest(assets, str(manifest_path))
        
        self.assertTrue(success)
        self.assertTrue(manifest_path.exists())
        
        # Verify manifest content
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
        
        self.assertEqual(manifest['total_assets'], 1)
        self.assertIn('icon', manifest['assets_by_type'])
        self.assertEqual(manifest['assets_by_type']['icon'], 1)
    
    def test_validate_extracted_assets(self):
        """Test asset validation"""
        # Create a test file
        test_file = Path(self.temp_dir) / 'test.svg'
        test_file.write_text('test content')
        
        assets = [
            AssetMetadata(
                node_id='1:1',
                name='Valid Asset',
                asset_type=AssetType.ICON,
                export_format=ExportFormat.SVG,
                file_name='test.svg',
                local_path=str(test_file),
                figma_url='https://figma.com/file/test',
                dimensions={'width': 24, 'height': 24},
                properties={},
                extracted_at='2024-01-01T00:00:00'
            ),
            AssetMetadata(
                node_id='1:2',
                name='Missing Asset',
                asset_type=AssetType.ICON,
                export_format=ExportFormat.SVG,
                file_name='missing.svg',
                local_path='/nonexistent/missing.svg',
                figma_url='https://figma.com/file/test',
                dimensions={},
                properties={},
                extracted_at='2024-01-01T00:00:00'
            )
        ]
        
        report = self.extractor.validate_extracted_assets(assets)
        
        self.assertEqual(report['total_assets'], 2)
        self.assertEqual(report['valid_assets'], 1)
        self.assertEqual(report['invalid_assets'], 1)
        self.assertIn('missing.svg', report['missing_files'])


class TestFigmaAssetService(TestCase):
    """Test cases for FigmaAssetService"""
    
    def setUp(self):
        self.temp_dir = _workspace_temp_dir()
        self.service = FigmaAssetService(self.temp_dir)
    
    def tearDown(self):
        # Clean up temp directory
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('dashboard.figma_asset_service.FigmaAssetService._get_figma_data_mcp')
    @patch('dashboard.figma_asset_service.FigmaAssetService._download_assets_mcp')
    def test_extract_assets_from_figma(self, mock_download, mock_get_data):
        """Test asset extraction from Figma"""
        # Mock Figma data
        mock_get_data.return_value = {
            'document': {
                'id': '0:0',
                'name': 'Document',
                'type': 'DOCUMENT',
                'children': [
                    {
                        'id': '1:1',
                        'name': 'Test Icon',
                        'type': 'VECTOR',
                        'absoluteBoundingBox': {'x': 0, 'y': 0, 'width': 24, 'height': 24}
                    }
                ]
            }
        }
        
        # Mock download result
        mock_download.return_value = {
            'downloaded': [
                {
                    'nodeId': '1:1',
                    'fileName': 'test-icon.svg',
                    'localPath': f'{self.temp_dir}/test-icon.svg',
                    'success': True
                }
            ],
            'errors': [],
            'total_requested': 1,
            'total_downloaded': 1,
            'total_errors': 0
        }
        
        result = self.service.extract_assets_from_figma(
            file_key='test123',
            asset_types=['icon']
        )
        
        self.assertTrue(result['success'])
        self.assertEqual(result['total_assets'], 1)
        self.assertEqual(len(result['assets']), 1)
        
        # Verify mock calls
        mock_get_data.assert_called_once_with('test123', None)
        mock_download.assert_called_once()
    
    @patch('dashboard.figma_asset_service.FigmaAssetService._get_figma_data_mcp')
    def test_extract_design_tokens(self, mock_get_data):
        """Test design token extraction"""
        # Mock Figma data with styles
        mock_get_data.return_value = {
            'styles': {
                'style1': {
                    'styleType': 'FILL',
                    'name': 'Primary Color',
                    'fills': [
                        {
                            'type': 'SOLID',
                            'color': {'r': 0.2, 'g': 0.4, 'b': 0.8},
                            'opacity': 1.0
                        }
                    ]
                }
            }
        }
        
        result = self.service.extract_design_tokens('test123')
        
        self.assertTrue(result['success'])
        self.assertIn('tokens', result)
        self.assertIn('css_variables', result)
        
        # Verify files were created
        tokens_path = Path(result['tokens_path'])
        css_path = Path(result['css_path'])
        
        self.assertTrue(tokens_path.exists())
        self.assertTrue(css_path.exists())
    
    def test_get_asset_inventory(self):
        """Test asset inventory generation"""
        # Create some test files
        test_dir = Path(self.temp_dir) / 'assets'
        test_dir.mkdir()
        
        (test_dir / 'icon1.svg').write_text('svg content')
        (test_dir / 'image1.png').write_text('png content')
        
        result = self.service.get_asset_inventory(str(test_dir))
        
        self.assertTrue(result['success'])
        
        inventory = result['inventory']
        self.assertEqual(inventory['total_files'], 2)
        self.assertIn('svg', inventory['files_by_format'])
        self.assertIn('png', inventory['files_by_format'])
    
    def test_organize_extracted_assets(self):
        """Test asset organization"""
        assets = [
            {
                'node_id': '1:1',
                'name': 'Icon 1',
                'asset_type': 'icon',
                'export_format': 'svg',
                'file_name': 'icon1.svg',
                'local_path': '/path/icon1.svg',
                'figma_url': 'https://figma.com/file/test',
                'dimensions': {},
                'properties': {},
                'extracted_at': '2024-01-01T00:00:00'
            },
            {
                'node_id': '1:2',
                'name': 'Image 1',
                'asset_type': 'image',
                'export_format': 'png',
                'file_name': 'image1.png',
                'local_path': '/path/image1.png',
                'figma_url': 'https://figma.com/file/test',
                'dimensions': {},
                'properties': {},
                'extracted_at': '2024-01-01T00:00:00'
            }
        ]
        
        organized = self.service.organize_extracted_assets(assets, 'type')
        
        self.assertIn('icon', organized)
        self.assertIn('image', organized)
        self.assertEqual(len(organized['icon']), 1)
        self.assertEqual(len(organized['image']), 1)


class TestBatchExtractionConfig(TestCase):
    """Test cases for BatchExtractionConfig"""
    
    def test_batch_config_creation(self):
        """Test batch configuration creation"""
        config = BatchExtractionConfig(
            file_key='test123',
            output_directory='/output',
            asset_types=[AssetType.ICON, AssetType.IMAGE],
            export_formats=[ExportFormat.SVG, ExportFormat.PNG],
            export_scales=[1.0, 2.0]
        )
        
        self.assertEqual(config.file_key, 'test123')
        self.assertEqual(config.output_directory, '/output')
        self.assertEqual(len(config.asset_types), 2)
        self.assertEqual(len(config.export_formats), 2)
        self.assertEqual(len(config.export_scales), 2)


class TestAssetMetadata(TestCase):
    """Test cases for AssetMetadata"""
    
    def test_asset_metadata_creation(self):
        """Test asset metadata creation"""
        metadata = AssetMetadata(
            node_id='1:123',
            name='Test Asset',
            asset_type=AssetType.ICON,
            export_format=ExportFormat.SVG,
            file_name='test.svg',
            local_path='/path/test.svg',
            figma_url='https://figma.com/file/test',
            dimensions={'width': 24, 'height': 24},
            properties={'type': 'VECTOR'},
            extracted_at='2024-01-01T00:00:00'
        )
        
        self.assertEqual(metadata.node_id, '1:123')
        self.assertEqual(metadata.name, 'Test Asset')
        self.assertEqual(metadata.asset_type, AssetType.ICON)
        self.assertEqual(metadata.export_format, ExportFormat.SVG)
        self.assertEqual(metadata.dimensions['width'], 24)


class TestUtilityFunctions(TestCase):
    """Test cases for utility functions"""
    
    def setUp(self):
        self.temp_dir = _workspace_temp_dir()
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_extract_all_icons(self):
        """Test extract_all_icons utility function"""
        from .figma_asset_extractor import extract_all_icons
        
        with patch('dashboard.figma_asset_extractor.FigmaAssetExtractor.extract_icons') as mock_extract:
            mock_extract.return_value = []
            
            result = extract_all_icons('test123', self.temp_dir)
            
            mock_extract.assert_called_once_with('test123', self.temp_dir)
            self.assertEqual(result, [])
    
    def test_extract_all_images(self):
        """Test extract_all_images utility function"""
        from .figma_asset_extractor import extract_all_images
        
        with patch('dashboard.figma_asset_extractor.FigmaAssetExtractor.extract_images') as mock_extract:
            mock_extract.return_value = []
            
            result = extract_all_images('test123', self.temp_dir)
            
            mock_extract.assert_called_once()
            self.assertEqual(result, [])


if __name__ == '__main__':
    unittest.main()
