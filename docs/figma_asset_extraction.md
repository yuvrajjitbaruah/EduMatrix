# Figma Asset Extraction Utilities

This document provides comprehensive documentation for the Figma asset extraction utilities implemented for the EduMatrix platform redesign.

## Overview

The Figma asset extraction utilities provide a complete solution for extracting, organizing, and managing design assets from Figma files. These utilities support various asset types, export formats, batch processing, and integration with the Figma API via MCP (Model Context Protocol) tools.

## Architecture

### Core Components

1. **FigmaAssetExtractor** - Main extraction engine
2. **FigmaAssetService** - Service layer with MCP integration
3. **AssetMetadata** - Data structure for asset information
4. **BatchExtractionConfig** - Configuration for batch operations
5. **Management Command** - Django command-line interface
6. **Utility Functions** - Convenience functions for common operations

### Asset Types Supported

- **Icons** - Vector graphics (SVG format preferred)
- **Images** - Raster graphics (PNG, JPG formats)
- **Components** - Figma components and component sets
- **SVG Graphics** - Vector illustrations and graphics
- **GIF Animations** - Animated graphics
- **Frames** - Layout frames and containers

### Export Formats

- **SVG** - Scalable vector graphics (recommended for icons)
- **PNG** - Portable network graphics (supports transparency)
- **JPG** - JPEG images (smaller file size, no transparency)
- **GIF** - Graphics interchange format (supports animation)

## Installation and Setup

### Prerequisites

1. Django project with Figma MCP server configured
2. Figma API key with appropriate permissions
3. Python packages: `pathlib`, `dataclasses`, `typing`

### Configuration

1. **MCP Configuration** (`.kiro/settings/mcp.json`):
```json
{
  "mcpServers": {
    "figma": {
      "command": "npx",
      "args": ["-y", "figma-developer-mcp", "--stdio"],
      "env": {
        "FIGMA_API_KEY": "your_figma_api_key_here"
      },
      "disabled": false
    }
  }
}
```

2. **Django Settings**:
```python
# Add to INSTALLED_APPS
INSTALLED_APPS = [
    # ... other apps
    'dashboard',
]

# Static files configuration
STATIC_URL = '/static/'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]
```

## Usage Guide

### Basic Asset Extraction

```python
from dashboard.figma_asset_service import FigmaAssetService

# Initialize service
service = FigmaAssetService("static/figma-assets")

# Extract assets from Figma file
result = service.extract_assets_from_figma(
    file_key="your_figma_file_key",
    asset_types=['icon', 'image'],
    output_directory="static/assets"
)

if result['success']:
    print(f"Extracted {result['total_assets']} assets")
else:
    print(f"Error: {result['error']}")
```

### Batch Asset Extraction

```python
# Configure batch extraction
config = {
    'output_directory': 'static/figma-assets',
    'asset_types': ['icon', 'image', 'component'],
    'export_formats': ['svg', 'png'],
    'export_scales': [1.0, 2.0, 3.0],
    'organize_by_type': True,
    'include_metadata': True
}

# Perform batch extraction
result = service.batch_extract_assets("file_key", config)
```

### Design Token Extraction

```python
# Extract design tokens (colors, typography, spacing, etc.)
tokens_result = service.extract_design_tokens("file_key")

if tokens_result['success']:
    # Tokens are saved as JSON and CSS files
    print(f"Tokens: {tokens_result['tokens_path']}")
    print(f"CSS: {tokens_result['css_path']}")
```

### Using Utility Functions

```python
from dashboard.figma_asset_extractor import (
    extract_all_icons, extract_all_images, extract_design_system_assets
)

# Extract all icons as SVG
icons = extract_all_icons("file_key", "static/icons")

# Extract all images with multiple scales
images = extract_all_images("file_key", "static/images", scales=[1.0, 2.0])

# Extract complete design system
design_assets = extract_design_system_assets("file_key", "static/design-system")
```

### Django Management Command

```bash
# Basic extraction
python manage.py extract_figma_assets --file-key YOUR_FILE_KEY

# Advanced extraction with options
python manage.py extract_figma_assets \
    --file-key YOUR_FILE_KEY \
    --asset-types icon image component \
    --export-formats svg png \
    --export-scales 1.0 2.0 3.0 \
    --output-dir static/figma-assets \
    --extract-tokens \
    --batch-mode

# Generate asset inventory
python manage.py extract_figma_assets \
    --inventory-only \
    --output-dir static/figma-assets

# Validate existing assets
python manage.py extract_figma_assets \
    --validate-only \
    --output-dir static/figma-assets
```

## API Reference

### FigmaAssetExtractor

#### Methods

##### `extract_single_asset(file_key, node_id, asset_type, export_format, output_path, scale=1.0, custom_name=None)`

Extract a single asset from Figma.

**Parameters:**
- `file_key` (str): Figma file key
- `node_id` (str): Node ID to extract
- `asset_type` (AssetType): Type of asset
- `export_format` (ExportFormat): Export format
- `output_path` (str): Local output path
- `scale` (float): Export scale for raster formats
- `custom_name` (str, optional): Custom filename

**Returns:** `AssetMetadata` object or `None`

##### `extract_batch_assets(config)`

Extract multiple assets in batch.

**Parameters:**
- `config` (BatchExtractionConfig): Batch extraction configuration

**Returns:** List of `AssetMetadata` objects

##### `extract_assets_by_type(file_key, asset_type, output_directory, export_format=None, scales=None)`

Extract all assets of a specific type.

**Parameters:**
- `file_key` (str): Figma file key
- `asset_type` (AssetType): Type of assets to extract
- `output_directory` (str): Output directory
- `export_format` (ExportFormat, optional): Export format
- `scales` (List[float], optional): Export scales

**Returns:** List of `AssetMetadata` objects

##### `organize_assets(assets, organization_scheme="type")`

Organize extracted assets by various schemes.

**Parameters:**
- `assets` (List[AssetMetadata]): List of asset metadata
- `organization_scheme` (str): "type", "format", "scale", or "name"

**Returns:** Dictionary of organized assets

##### `generate_asset_manifest(assets, output_path)`

Generate a manifest file for extracted assets.

**Parameters:**
- `assets` (List[AssetMetadata]): List of asset metadata
- `output_path` (str): Path for manifest file

**Returns:** `bool` - Success status

##### `validate_extracted_assets(assets)`

Validate extracted assets for completeness and quality.

**Parameters:**
- `assets` (List[AssetMetadata]): List of asset metadata

**Returns:** Dictionary with validation report

### FigmaAssetService

#### Methods

##### `extract_assets_from_figma(file_key, node_id=None, asset_types=None, output_directory=None)`

Extract assets from Figma using MCP tools.

**Parameters:**
- `file_key` (str): Figma file key
- `node_id` (str, optional): Specific node ID
- `asset_types` (List[str], optional): Asset types to extract
- `output_directory` (str, optional): Output directory

**Returns:** Dictionary with extraction results

##### `extract_design_tokens(file_key)`

Extract design tokens from Figma file.

**Parameters:**
- `file_key` (str): Figma file key

**Returns:** Dictionary with design tokens and CSS variables

##### `batch_extract_assets(file_key, config)`

Perform batch asset extraction.

**Parameters:**
- `file_key` (str): Figma file key
- `config` (Dict): Batch extraction configuration

**Returns:** Dictionary with batch extraction results

##### `get_asset_inventory(directory=None)`

Get inventory of assets in directory.

**Parameters:**
- `directory` (str, optional): Directory to scan

**Returns:** Dictionary with asset inventory

### Data Structures

#### AssetMetadata

```python
@dataclass
class AssetMetadata:
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
```

#### BatchExtractionConfig

```python
@dataclass
class BatchExtractionConfig:
    file_key: str
    output_directory: str
    asset_types: List[AssetType]
    export_formats: List[ExportFormat]
    export_scales: List[float]
    naming_convention: str = "descriptive"
    organize_by_type: bool = True
    include_metadata: bool = True
    overwrite_existing: bool = False
```

## File Organization

### Default Directory Structure

```
static/figma-assets/
├── icons/
│   ├── svg/
│   │   ├── icon-name.svg
│   │   └── icon-name@2x.svg
│   └── png/
│       ├── icon-name.png
│       └── icon-name@2x.png
├── images/
│   ├── png/
│   │   ├── image-name.png
│   │   └── image-name@2x.png
│   └── jpg/
│       └── image-name.jpg
├── components/
│   └── svg/
│       └── component-name.svg
├── design-tokens.json
├── design-tokens.css
├── asset_manifest.json
└── extraction_metadata.json
```

### Asset Naming Conventions

#### Descriptive Naming (Default)
- Format: `{sanitized-name}[@{scale}x].{extension}`
- Example: `user-profile-icon@2x.png`

#### Node ID Naming
- Format: `{node-id}[@{scale}x].{extension}`
- Example: `1-123@2x.png`

#### Custom Naming
- User-defined naming pattern
- Supports placeholders: `{name}`, `{id}`, `{type}`, `{scale}`

## Asset Manifest Format

The asset manifest is a JSON file containing metadata about all extracted assets:

```json
{
  "generated_at": "2024-01-01T00:00:00Z",
  "total_assets": 25,
  "assets_by_type": {
    "icon": 15,
    "image": 8,
    "component": 2
  },
  "assets": [
    {
      "node_id": "1:123",
      "name": "User Icon",
      "asset_type": "icon",
      "export_format": "svg",
      "file_name": "user-icon.svg",
      "local_path": "static/icons/svg/user-icon.svg",
      "figma_url": "https://figma.com/file/abc123?node-id=1:123",
      "dimensions": {"width": 24, "height": 24},
      "properties": {"type": "VECTOR"},
      "extracted_at": "2024-01-01T00:00:00Z"
    }
  ]
}
```

## Design Tokens

### Supported Token Types

1. **Colors** - Fill styles from Figma
2. **Typography** - Text styles (font family, size, weight, line height)
3. **Spacing** - Padding and margin values
4. **Shadows** - Drop shadow effects
5. **Border Radius** - Corner radius values

### CSS Variables Output

```css
:root {
  /* Colors */
  --color-primary: rgb(99, 102, 241);
  --color-secondary: rgb(168, 85, 247);
  
  /* Typography */
  --font-heading-family: 'Inter';
  --font-heading-size: 24px;
  --font-heading-weight: 600;
  
  /* Spacing */
  --space-small: 8px;
  --space-medium: 16px;
  --space-large: 24px;
  
  /* Shadows */
  --shadow-card: 0px 4px 24px rgba(0, 0, 0, 0.06);
  
  /* Border Radius */
  --radius-small: 4px;
  --radius-medium: 8px;
}
```

## Error Handling

### Common Errors

1. **Authentication Errors**
   - Invalid Figma API key
   - Insufficient permissions

2. **File/Node Errors**
   - Invalid file key
   - Node not found
   - File not accessible

3. **Network Errors**
   - Connection timeout
   - Rate limiting
   - API unavailable

4. **File System Errors**
   - Permission denied
   - Disk space full
   - Invalid path

### Error Recovery

```python
try:
    result = service.extract_assets_from_figma(file_key, asset_types=['icon'])
except FigmaAuthError as e:
    print(f"Authentication failed: {e}")
    # Check API key configuration
except FigmaNotFoundError as e:
    print(f"File/node not found: {e}")
    # Verify file key and node ID
except FigmaRateLimitError as e:
    print(f"Rate limit exceeded: {e}")
    # Implement retry with backoff
except Exception as e:
    print(f"Unexpected error: {e}")
    # Log error and continue with fallback
```

## Performance Considerations

### Optimization Strategies

1. **Batch Processing** - Extract multiple assets in single API call
2. **Caching** - Cache Figma data to reduce API calls
3. **Parallel Downloads** - Download assets concurrently
4. **Incremental Updates** - Only extract changed assets
5. **Compression** - Optimize asset file sizes

### Rate Limiting

- Figma API has rate limits (typically 100 requests per minute)
- Implement exponential backoff for rate limit errors
- Use batch operations to reduce API calls
- Cache frequently accessed data

### Memory Management

- Process large files in chunks
- Clean up temporary files
- Use generators for large asset lists
- Monitor memory usage during batch operations

## Testing

### Unit Tests

Run the test suite:

```bash
python manage.py test dashboard.tests_figma_assets
```

### Test Coverage

- Asset extraction functionality
- Error handling scenarios
- File system operations
- Data validation
- Utility functions

### Mock Testing

Tests use mocked Figma API responses to avoid external dependencies:

```python
@patch('dashboard.figma_asset_service.FigmaAssetService._get_figma_data_mcp')
def test_extract_assets(self, mock_get_data):
    mock_get_data.return_value = mock_figma_data
    result = service.extract_assets_from_figma("test_key")
    self.assertTrue(result['success'])
```

## Integration with EduMatrix

### Template Integration

Use extracted assets in Django templates:

```html
<!-- Icons -->
<img src="{% static 'figma-assets/icons/svg/user-icon.svg' %}" alt="User">

<!-- Images with responsive scaling -->
<img src="{% static 'figma-assets/images/png/hero-image.png' %}"
     srcset="{% static 'figma-assets/images/png/hero-image@2x.png' %} 2x"
     alt="Hero Image">

<!-- CSS Variables -->
<link rel="stylesheet" href="{% static 'figma-assets/design-tokens.css' %}">
```

### CSS Integration

```css
/* Use extracted design tokens */
.button {
  background-color: var(--color-primary);
  border-radius: var(--radius-medium);
  padding: var(--space-small) var(--space-medium);
  box-shadow: var(--shadow-card);
}

/* Use extracted icons as backgrounds */
.icon-user {
  background-image: url('../figma-assets/icons/svg/user-icon.svg');
  background-size: contain;
  background-repeat: no-repeat;
}
```

### Automated Workflows

Set up automated asset extraction in CI/CD:

```yaml
# GitHub Actions example
- name: Extract Figma Assets
  run: |
    python manage.py extract_figma_assets \
      --file-key ${{ secrets.FIGMA_FILE_KEY }} \
      --batch-mode \
      --extract-tokens
```

## Troubleshooting

### Common Issues

1. **"Figma API returned 403 Forbidden"**
   - Check API key permissions
   - Verify file sharing settings
   - Ensure file is accessible to API token owner

2. **"Invalid file key format"**
   - Extract file key from Figma URL correctly
   - Format: `figma.com/file/{FILE_KEY}/...`

3. **"Assets not downloading"**
   - Check network connectivity
   - Verify output directory permissions
   - Check available disk space

4. **"Empty or corrupted assets"**
   - Verify node types are supported
   - Check export format compatibility
   - Validate Figma file structure

### Debug Mode

Enable debug logging:

```python
import logging
logging.getLogger('dashboard.figma_asset_extractor').setLevel(logging.DEBUG)
```

### Support Resources

- [Figma API Documentation](https://www.figma.com/developers/api)
- [MCP Figma Server](https://github.com/figma/figma-developer-mcp)
- [EduMatrix Documentation](./README.md)

## Best Practices

### Asset Organization

1. **Consistent Naming** - Use descriptive, consistent naming conventions
2. **Type Separation** - Organize assets by type in separate directories
3. **Scale Variants** - Provide multiple scales for raster images
4. **Format Selection** - Use SVG for icons, PNG for images with transparency
5. **Metadata Tracking** - Always generate and maintain asset manifests

### Performance

1. **Batch Operations** - Use batch extraction for multiple assets
2. **Incremental Updates** - Only extract changed assets
3. **Caching Strategy** - Cache Figma data and reuse when possible
4. **Asset Optimization** - Optimize file sizes post-extraction
5. **Monitoring** - Track extraction performance and errors

### Maintenance

1. **Regular Updates** - Sync with Figma design changes
2. **Validation Checks** - Regularly validate asset integrity
3. **Cleanup** - Remove unused or outdated assets
4. **Documentation** - Keep asset documentation up to date
5. **Version Control** - Track asset changes in version control

## Conclusion

The Figma asset extraction utilities provide a comprehensive solution for managing design assets in the EduMatrix platform. They support automated extraction, organization, and validation of various asset types while maintaining synchronization with Figma designs.

For additional support or feature requests, please refer to the project documentation or contact the development team.