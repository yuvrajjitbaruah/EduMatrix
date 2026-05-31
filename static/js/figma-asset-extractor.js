/**
 * Figma Asset Extraction Utilities (Client-side)
 * Provides client-side utilities for managing and organizing Figma assets
 */

class FigmaAssetExtractor {
    constructor() {
        this.extractedAssets = [];
        this.assetTypes = {
            IMAGE: 'image',
            ICON: 'icon',
            SVG: 'svg',
            GIF: 'gif',
            COMPONENT: 'component',
            FRAME: 'frame'
        };
        
        this.exportFormats = {
            SVG: 'svg',
            PNG: 'png',
            JPG: 'jpg',
            GIF: 'gif'
        };
        
        this.defaultScales = {
            [this.assetTypes.ICON]: [1.0, 2.0],
            [this.assetTypes.IMAGE]: [1.0, 2.0, 3.0],
            [this.assetTypes.SVG]: [1.0],
            [this.assetTypes.GIF]: [1.0]
        };
    }

    /**
     * Create asset metadata object
     * @param {Object} params - Asset parameters
     * @returns {Object} - Asset metadata
     */
    createAssetMetadata(params) {
        return {
            nodeId: params.nodeId,
            name: params.name,
            assetType: params.assetType,
            exportFormat: params.exportFormat,
            fileName: params.fileName,
            localPath: params.localPath,
            figmaUrl: params.figmaUrl,
            dimensions: params.dimensions || {},
            properties: params.properties || {},
            extractedAt: new Date().toISOString(),
            imageRef: params.imageRef || null,
            gifRef: params.gifRef || null,
            cropTransform: params.cropTransform || null,
            needsCropping: params.needsCropping || false,
            requiresDimensions: params.requiresDimensions || false
        };
    }

    /**
     * Generate asset filename from node data
     * @param {Object} nodeData - Node data from Figma
     * @param {string} extension - File extension
     * @param {number} scale - Export scale
     * @returns {string} - Generated filename
     */
    generateAssetFilename(nodeData, extension = 'svg', scale = 1.0) {
        const name = nodeData.name || 'asset';
        const sanitized = name
            .toLowerCase()
            .replace(/[^a-z0-9]/g, '-')
            .replace(/-+/g, '-')
            .replace(/^-|-$/g, '');
        
        const scalePrefix = scale !== 1.0 ? `@${scale}x` : '';
        return `${sanitized}${scalePrefix}.${extension}`;
    }

    /**
     * Extract asset properties from node data
     * @param {Object} nodeData - Node data from Figma
     * @returns {Object} - Extracted properties
     */
    extractAssetProperties(nodeData) {
        return {
            type: nodeData.type,
            visible: nodeData.visible !== false,
            opacity: nodeData.opacity || 1.0,
            blendMode: nodeData.blendMode,
            fills: nodeData.fills || [],
            strokes: nodeData.strokes || [],
            effects: nodeData.effects || [],
            cornerRadius: nodeData.cornerRadius,
            constraints: nodeData.constraints || {}
        };
    }

    /**
     * Extract dimensions from node data
     * @param {Object} nodeData - Node data from Figma
     * @returns {Object} - Dimensions object
     */
    extractDimensions(nodeData) {
        const bbox = nodeData.absoluteBoundingBox || {};
        return {
            width: bbox.width || 0,
            height: bbox.height || 0,
            x: bbox.x || 0,
            y: bbox.y || 0
        };
    }

    /**
     * Check if node is valid for asset type
     * @param {Object} nodeData - Node data
     * @param {string} assetType - Asset type
     * @returns {boolean} - True if valid
     */
    isValidNodeForAssetType(nodeData, assetType) {
        const supportedTypes = {
            [this.assetTypes.IMAGE]: ['RECTANGLE', 'ELLIPSE', 'FRAME', 'GROUP'],
            [this.assetTypes.ICON]: ['VECTOR', 'BOOLEAN_OPERATION', 'FRAME', 'GROUP'],
            [this.assetTypes.SVG]: ['VECTOR', 'BOOLEAN_OPERATION', 'FRAME', 'GROUP'],
            [this.assetTypes.COMPONENT]: ['COMPONENT', 'COMPONENT_SET'],
            [this.assetTypes.FRAME]: ['FRAME']
        };
        
        const nodeType = nodeData.type;
        const supported = supportedTypes[assetType] || [];
        return supported.includes(nodeType);
    }

    /**
     * Check if export format is compatible with asset type
     * @param {string} exportFormat - Export format
     * @param {string} assetType - Asset type
     * @returns {boolean} - True if compatible
     */
    isCompatibleFormatType(exportFormat, assetType) {
        const compatible = {
            [this.assetTypes.ICON]: [this.exportFormats.SVG, this.exportFormats.PNG],
            [this.assetTypes.SVG]: [this.exportFormats.SVG],
            [this.assetTypes.IMAGE]: [this.exportFormats.PNG, this.exportFormats.JPG],
            [this.assetTypes.GIF]: [this.exportFormats.GIF, this.exportFormats.PNG],
            [this.assetTypes.COMPONENT]: [this.exportFormats.SVG, this.exportFormats.PNG],
            [this.assetTypes.FRAME]: [this.exportFormats.PNG, this.exportFormats.JPG, this.exportFormats.SVG]
        };
        
        return (compatible[assetType] || []).includes(exportFormat);
    }

    /**
     * Get default export format for asset type
     * @param {string} assetType - Asset type
     * @returns {string} - Default export format
     */
    getDefaultFormat(assetType) {
        const defaults = {
            [this.assetTypes.ICON]: this.exportFormats.SVG,
            [this.assetTypes.SVG]: this.exportFormats.SVG,
            [this.assetTypes.IMAGE]: this.exportFormats.PNG,
            [this.assetTypes.GIF]: this.exportFormats.GIF,
            [this.assetTypes.COMPONENT]: this.exportFormats.SVG,
            [this.assetTypes.FRAME]: this.exportFormats.PNG
        };
        
        return defaults[assetType] || this.exportFormats.PNG;
    }

    /**
     * Find extractable nodes in Figma data
     * @param {Object} fileData - Complete Figma file data
     * @param {Array} assetTypes - Asset types to look for
     * @returns {Array} - Array of extractable nodes
     */
    findExtractableNodes(fileData, assetTypes) {
        const extractable = [];
        
        const traverseNode = (node) => {
            // Check if node is extractable for any requested asset type
            for (const assetType of assetTypes) {
                if (this.isValidNodeForAssetType(node, assetType)) {
                    extractable.push(node);
                    break;
                }
            }
            
            // Traverse children
            if (node.children) {
                node.children.forEach(child => traverseNode(child));
            }
        };
        
        if (fileData.document) {
            traverseNode(fileData.document);
        }
        
        return extractable;
    }

    /**
     * Organize assets by various schemes
     * @param {Array} assets - Array of asset metadata
     * @param {string} scheme - Organization scheme ('type', 'format', 'scale', 'name')
     * @returns {Object} - Organized assets
     */
    organizeAssets(assets, scheme = 'type') {
        const organized = {};
        
        assets.forEach(asset => {
            let key;
            
            switch (scheme) {
                case 'type':
                    key = asset.assetType;
                    break;
                case 'format':
                    key = asset.exportFormat;
                    break;
                case 'scale':
                    key = `scale_${this.extractScaleFromAsset(asset)}`;
                    break;
                case 'name':
                    key = this.extractBaseName(asset.name);
                    break;
                default:
                    key = 'all';
            }
            
            if (!organized[key]) {
                organized[key] = [];
            }
            organized[key].push(asset);
        });
        
        return organized;
    }

    /**
     * Extract scale information from asset
     * @param {Object} asset - Asset metadata
     * @returns {string} - Scale value
     */
    extractScaleFromAsset(asset) {
        const match = asset.fileName.match(/@(\d+(?:\.\d+)?)x/);
        return match ? match[1] : '1.0';
    }

    /**
     * Extract base name without scale/format suffixes
     * @param {string} name - Asset name
     * @returns {string} - Base name
     */
    extractBaseName(name) {
        return name
            .replace(/@\d+(?:\.\d+)?x/, '')
            .replace(/\.[^.]+$/, '');
    }

    /**
     * Generate asset manifest
     * @param {Array} assets - Array of asset metadata
     * @returns {Object} - Asset manifest
     */
    generateAssetManifest(assets) {
        const manifest = {
            generatedAt: new Date().toISOString(),
            totalAssets: assets.length,
            assetsByType: {},
            assets: assets
        };
        
        // Count by type
        assets.forEach(asset => {
            const type = asset.assetType;
            manifest.assetsByType[type] = (manifest.assetsByType[type] || 0) + 1;
        });
        
        return manifest;
    }

    /**
     * Validate extracted assets
     * @param {Array} assets - Array of asset metadata
     * @returns {Object} - Validation report
     */
    validateExtractedAssets(assets) {
        const report = {
            totalAssets: assets.length,
            validAssets: 0,
            invalidAssets: 0,
            missingProperties: [],
            invalidDimensions: [],
            errors: []
        };
        
        assets.forEach(asset => {
            try {
                // Check required properties
                const requiredProps = ['nodeId', 'name', 'assetType', 'exportFormat', 'fileName'];
                const missingProps = requiredProps.filter(prop => !asset[prop]);
                
                if (missingProps.length > 0) {
                    report.missingProperties.push({
                        asset: asset.name || 'Unknown',
                        missing: missingProps
                    });
                    report.invalidAssets++;
                    return;
                }
                
                // Check dimensions for raster formats
                if (['png', 'jpg'].includes(asset.exportFormat)) {
                    if (!asset.dimensions || asset.dimensions.width <= 0) {
                        report.invalidDimensions.push(asset.fileName);
                        report.invalidAssets++;
                        return;
                    }
                }
                
                report.validAssets++;
                
            } catch (error) {
                report.errors.push(`Error validating ${asset.fileName}: ${error.message}`);
                report.invalidAssets++;
            }
        });
        
        return report;
    }

    /**
     * Create batch extraction configuration
     * @param {Object} params - Configuration parameters
     * @returns {Object} - Batch configuration
     */
    createBatchConfig(params) {
        return {
            fileKey: params.fileKey,
            outputDirectory: params.outputDirectory,
            assetTypes: params.assetTypes || [this.assetTypes.ICON, this.assetTypes.IMAGE],
            exportFormats: params.exportFormats || [this.exportFormats.SVG, this.exportFormats.PNG],
            exportScales: params.exportScales || [1.0, 2.0],
            namingConvention: params.namingConvention || 'descriptive',
            organizeByType: params.organizeByType !== false,
            includeMetadata: params.includeMetadata !== false,
            overwriteExisting: params.overwriteExisting || false
        };
    }

    /**
     * Filter assets by criteria
     * @param {Array} assets - Array of asset metadata
     * @param {Object} criteria - Filter criteria
     * @returns {Array} - Filtered assets
     */
    filterAssets(assets, criteria) {
        return assets.filter(asset => {
            // Filter by asset type
            if (criteria.assetType && asset.assetType !== criteria.assetType) {
                return false;
            }
            
            // Filter by export format
            if (criteria.exportFormat && asset.exportFormat !== criteria.exportFormat) {
                return false;
            }
            
            // Filter by minimum dimensions
            if (criteria.minWidth && asset.dimensions.width < criteria.minWidth) {
                return false;
            }
            
            if (criteria.minHeight && asset.dimensions.height < criteria.minHeight) {
                return false;
            }
            
            // Filter by name pattern
            if (criteria.namePattern) {
                const regex = new RegExp(criteria.namePattern, 'i');
                if (!regex.test(asset.name)) {
                    return false;
                }
            }
            
            return true;
        });
    }

    /**
     * Get asset statistics
     * @param {Array} assets - Array of asset metadata
     * @returns {Object} - Asset statistics
     */
    getAssetStatistics(assets) {
        const stats = {
            total: assets.length,
            byType: {},
            byFormat: {},
            byScale: {},
            totalSize: 0,
            averageDimensions: { width: 0, height: 0 }
        };
        
        let totalWidth = 0;
        let totalHeight = 0;
        let dimensionCount = 0;
        
        assets.forEach(asset => {
            // Count by type
            stats.byType[asset.assetType] = (stats.byType[asset.assetType] || 0) + 1;
            
            // Count by format
            stats.byFormat[asset.exportFormat] = (stats.byFormat[asset.exportFormat] || 0) + 1;
            
            // Count by scale
            const scale = this.extractScaleFromAsset(asset);
            stats.byScale[scale] = (stats.byScale[scale] || 0) + 1;
            
            // Calculate average dimensions
            if (asset.dimensions && asset.dimensions.width > 0) {
                totalWidth += asset.dimensions.width;
                totalHeight += asset.dimensions.height;
                dimensionCount++;
            }
        });
        
        if (dimensionCount > 0) {
            stats.averageDimensions.width = Math.round(totalWidth / dimensionCount);
            stats.averageDimensions.height = Math.round(totalHeight / dimensionCount);
        }
        
        return stats;
    }

    /**
     * Export asset data as JSON
     * @param {Array} assets - Array of asset metadata
     * @param {string} filename - Export filename
     */
    exportAssetData(assets, filename = 'figma-assets.json') {
        const data = {
            exportedAt: new Date().toISOString(),
            assets: assets,
            statistics: this.getAssetStatistics(assets)
        };
        
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    /**
     * Import asset data from JSON
     * @param {File} file - JSON file to import
     * @returns {Promise<Array>} - Promise resolving to imported assets
     */
    importAssetData(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            
            reader.onload = (e) => {
                try {
                    const data = JSON.parse(e.target.result);
                    const assets = data.assets || [];
                    resolve(assets);
                } catch (error) {
                    reject(new Error('Invalid JSON file'));
                }
            };
            
            reader.onerror = () => reject(new Error('Error reading file'));
            reader.readAsText(file);
        });
    }
}

// Utility functions for common operations

/**
 * Create a new asset extractor instance
 * @returns {FigmaAssetExtractor} - New extractor instance
 */
function createAssetExtractor() {
    return new FigmaAssetExtractor();
}

/**
 * Quick asset organization by type
 * @param {Array} assets - Array of asset metadata
 * @returns {Object} - Assets organized by type
 */
function organizeAssetsByType(assets) {
    const extractor = new FigmaAssetExtractor();
    return extractor.organizeAssets(assets, 'type');
}

/**
 * Quick asset validation
 * @param {Array} assets - Array of asset metadata
 * @returns {Object} - Validation report
 */
function validateAssets(assets) {
    const extractor = new FigmaAssetExtractor();
    return extractor.validateExtractedAssets(assets);
}

/**
 * Generate asset manifest
 * @param {Array} assets - Array of asset metadata
 * @returns {Object} - Asset manifest
 */
function generateManifest(assets) {
    const extractor = new FigmaAssetExtractor();
    return extractor.generateAssetManifest(assets);
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        FigmaAssetExtractor,
        createAssetExtractor,
        organizeAssetsByType,
        validateAssets,
        generateManifest
    };
} else {
    window.FigmaAssetExtractor = FigmaAssetExtractor;
    window.createAssetExtractor = createAssetExtractor;
    window.organizeAssetsByType = organizeAssetsByType;
    window.validateAssets = validateAssets;
    window.generateManifest = generateManifest;
}