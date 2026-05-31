"""
Django management command for extracting Figma assets
Usage: python manage.py extract_figma_assets --file-key <key> [options]
"""

import json
import sys
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from dashboard.figma_asset_service import FigmaAssetService


class Command(BaseCommand):
    help = 'Extract assets from Figma files using the asset extraction utilities'

    def add_arguments(self, parser):
        # Required arguments
        parser.add_argument(
            '--file-key',
            type=str,
            required=True,
            help='Figma file key to extract assets from'
        )
        
        # Optional arguments
        parser.add_argument(
            '--node-id',
            type=str,
            help='Specific node ID to extract (optional)'
        )
        
        parser.add_argument(
            '--asset-types',
            nargs='+',
            choices=['icon', 'image', 'svg', 'gif', 'component', 'frame'],
            default=['icon', 'image'],
            help='Types of assets to extract (default: icon image)'
        )
        
        parser.add_argument(
            '--output-dir',
            type=str,
            default='static/figma-assets',
            help='Output directory for extracted assets (default: static/figma-assets)'
        )
        
        parser.add_argument(
            '--export-formats',
            nargs='+',
            choices=['svg', 'png', 'jpg', 'gif'],
            default=['svg', 'png'],
            help='Export formats (default: svg png)'
        )
        
        parser.add_argument(
            '--export-scales',
            nargs='+',
            type=float,
            default=[1.0, 2.0],
            help='Export scales for raster formats (default: 1.0 2.0)'
        )
        
        parser.add_argument(
            '--organize-by-type',
            action='store_true',
            default=True,
            help='Organize assets by type in subdirectories'
        )
        
        parser.add_argument(
            '--extract-tokens',
            action='store_true',
            help='Also extract design tokens from the file'
        )
        
        parser.add_argument(
            '--batch-mode',
            action='store_true',
            help='Use batch extraction mode'
        )
        
        parser.add_argument(
            '--validate-only',
            action='store_true',
            help='Only validate existing assets without extracting'
        )
        
        parser.add_argument(
            '--inventory-only',
            action='store_true',
            help='Only generate asset inventory without extracting'
        )
        
        parser.add_argument(
            '--output-format',
            choices=['json', 'text'],
            default='text',
            help='Output format for results (default: text)'
        )

    def handle(self, *args, **options):
        try:
            # Initialize service
            service = FigmaAssetService(options['output_dir'])
            
            # Handle inventory-only mode
            if options['inventory_only']:
                self._handle_inventory_only(service, options)
                return
            
            # Handle validate-only mode
            if options['validate_only']:
                self._handle_validate_only(service, options)
                return
            
            # Extract design tokens if requested
            if options['extract_tokens']:
                self._extract_design_tokens(service, options)
            
            # Extract assets
            if options['batch_mode']:
                result = self._extract_batch_assets(service, options)
            else:
                result = self._extract_single_assets(service, options)
            
            # Output results
            self._output_results(result, options)
            
        except Exception as e:
            raise CommandError(f'Asset extraction failed: {e}')

    def _extract_single_assets(self, service, options):
        """Extract assets using single extraction mode"""
        self.stdout.write('Extracting assets from Figma...')
        
        result = service.extract_assets_from_figma(
            file_key=options['file_key'],
            node_id=options.get('node_id'),
            asset_types=options['asset_types'],
            output_directory=options['output_dir']
        )
        
        return result

    def _extract_batch_assets(self, service, options):
        """Extract assets using batch extraction mode"""
        self.stdout.write('Performing batch asset extraction...')
        
        config = {
            'output_directory': options['output_dir'],
            'asset_types': options['asset_types'],
            'export_formats': options['export_formats'],
            'export_scales': options['export_scales'],
            'organize_by_type': options['organize_by_type'],
            'include_metadata': True,
            'overwrite_existing': True
        }
        
        result = service.batch_extract_assets(options['file_key'], config)
        return result

    def _extract_design_tokens(self, service, options):
        """Extract design tokens from Figma"""
        self.stdout.write('Extracting design tokens...')
        
        tokens_result = service.extract_design_tokens(options['file_key'])
        
        if tokens_result['success']:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Design tokens extracted successfully:\n'
                    f'  - Tokens file: {tokens_result["tokens_path"]}\n'
                    f'  - CSS file: {tokens_result["css_path"]}'
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(
                    f'Design token extraction failed: {tokens_result["error"]}'
                )
            )

    def _handle_inventory_only(self, service, options):
        """Handle inventory-only mode"""
        self.stdout.write('Generating asset inventory...')
        
        inventory_result = service.get_asset_inventory(options['output_dir'])
        
        if inventory_result['success']:
            inventory = inventory_result['inventory']
            
            if options['output_format'] == 'json':
                self.stdout.write(json.dumps(inventory, indent=2))
            else:
                self._output_inventory_text(inventory)
        else:
            self.stdout.write(
                self.style.ERROR(
                    f'Inventory generation failed: {inventory_result["error"]}'
                )
            )

    def _handle_validate_only(self, service, options):
        """Handle validate-only mode"""
        self.stdout.write('Validating existing assets...')
        
        # Load existing assets from manifest
        manifest_path = Path(options['output_dir']) / 'asset_manifest.json'
        
        if not manifest_path.exists():
            self.stdout.write(
                self.style.ERROR(
                    f'No asset manifest found at {manifest_path}. '
                    'Run extraction first to generate manifest.'
                )
            )
            return
        
        try:
            with open(manifest_path, 'r') as f:
                manifest = json.load(f)
            
            assets = manifest.get('assets', [])
            
            # Convert to AssetMetadata objects for validation
            from dashboard.figma_asset_extractor import AssetMetadata, AssetType, ExportFormat
            
            asset_objects = []
            for asset_dict in assets:
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
            
            # Validate assets
            validation_report = service.extractor.validate_extracted_assets(asset_objects)
            
            if options['output_format'] == 'json':
                self.stdout.write(json.dumps(validation_report, indent=2))
            else:
                self._output_validation_text(validation_report)
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Validation failed: {e}')
            )

    def _output_results(self, result, options):
        """Output extraction results"""
        if options['output_format'] == 'json':
            self.stdout.write(json.dumps(result, indent=2))
        else:
            self._output_results_text(result)

    def _output_results_text(self, result):
        """Output results in text format"""
        if result['success']:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Asset extraction completed successfully!\n'
                    f'Total assets extracted: {result["total_assets"]}\n'
                )
            )
            
            if 'manifest_path' in result:
                self.stdout.write(f'Manifest saved to: {result["manifest_path"]}')
            
            # Show asset breakdown
            if result['assets']:
                asset_types = {}
                for asset in result['assets']:
                    asset_type = asset['asset_type']
                    asset_types[asset_type] = asset_types.get(asset_type, 0) + 1
                
                self.stdout.write('\nAssets by type:')
                for asset_type, count in asset_types.items():
                    self.stdout.write(f'  - {asset_type}: {count}')
            
            # Show download results if available
            if 'download_result' in result:
                download = result['download_result']
                self.stdout.write(
                    f'\nDownload summary:\n'
                    f'  - Requested: {download["total_requested"]}\n'
                    f'  - Downloaded: {download["total_downloaded"]}\n'
                    f'  - Errors: {download["total_errors"]}'
                )
                
                if download['errors']:
                    self.stdout.write('\nDownload errors:')
                    for error in download['errors']:
                        self.stdout.write(
                            self.style.ERROR(
                                f'  - {error["fileName"]}: {error["error"]}'
                            )
                        )
        else:
            self.stdout.write(
                self.style.ERROR(
                    f'Asset extraction failed: {result["error"]}'
                )
            )

    def _output_inventory_text(self, inventory):
        """Output inventory in text format"""
        self.stdout.write(
            f'Asset Inventory for: {inventory["directory"]}\n'
            f'Scanned at: {inventory["scanned_at"]}\n'
            f'Total files: {inventory["total_files"]}\n'
            f'Total size: {inventory["total_size_bytes"]} bytes\n'
        )
        
        self.stdout.write('\nFiles by type:')
        for asset_type, count in inventory['files_by_type'].items():
            self.stdout.write(f'  - {asset_type}: {count}')
        
        self.stdout.write('\nFiles by format:')
        for format_type, count in inventory['files_by_format'].items():
            self.stdout.write(f'  - {format_type}: {count}')

    def _output_validation_text(self, validation_report):
        """Output validation report in text format"""
        self.stdout.write(
            f'Asset Validation Report\n'
            f'Total assets: {validation_report["total_assets"]}\n'
            f'Valid assets: {validation_report["valid_assets"]}\n'
            f'Invalid assets: {validation_report["invalid_assets"]}\n'
        )
        
        if validation_report['missing_files']:
            self.stdout.write('\nMissing files:')
            for filename in validation_report['missing_files']:
                self.stdout.write(self.style.ERROR(f'  - {filename}'))
        
        if validation_report['invalid_dimensions']:
            self.stdout.write('\nInvalid dimensions:')
            for filename in validation_report['invalid_dimensions']:
                self.stdout.write(self.style.WARNING(f'  - {filename}'))
        
        if validation_report['errors']:
            self.stdout.write('\nValidation errors:')
            for error in validation_report['errors']:
                self.stdout.write(self.style.ERROR(f'  - {error}'))
        
        if validation_report['valid_assets'] == validation_report['total_assets']:
            self.stdout.write(self.style.SUCCESS('\nAll assets are valid!'))
        else:
            self.stdout.write(
                self.style.WARNING(
                    f'\n{validation_report["invalid_assets"]} assets need attention.'
                )
            )