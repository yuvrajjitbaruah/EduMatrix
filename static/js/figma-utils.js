/**
 * Figma API Utility Functions
 * Provides helper functions for Figma integration and asset management
 */

class FigmaUtils {
    constructor() {
        this.apiBaseUrl = 'https://api.figma.com/v1';
        this.retryAttempts = 3;
        this.retryDelay = 1000; // 1 second
    }

    /**
     * Extract file key from Figma URL
     * @param {string} figmaUrl - Full Figma URL
     * @returns {string|null} - File key or null if invalid
     */
    extractFileKey(figmaUrl) {
        try {
            const regex = /figma\.com\/(file|design)\/([a-zA-Z0-9]+)/;
            const match = figmaUrl.match(regex);
            return match ? match[2] : null;
        } catch (error) {
            console.error('Error extracting file key:', error);
            return null;
        }
    }

    /**
     * Extract node ID from Figma URL
     * @param {string} figmaUrl - Full Figma URL with node-id parameter
     * @returns {string|null} - Node ID or null if not found
     */
    extractNodeId(figmaUrl) {
        try {
            const url = new URL(figmaUrl);
            const nodeId = url.searchParams.get('node-id');
            return nodeId ? nodeId.replace('-', ':') : null;
        } catch (error) {
            console.error('Error extracting node ID:', error);
            return null;
        }
    }

    /**
     * Validate Figma file key format
     * @param {string} fileKey - File key to validate
     * @returns {boolean} - True if valid format
     */
    isValidFileKey(fileKey) {
        const regex = /^[a-zA-Z0-9]+$/;
        return regex.test(fileKey) && fileKey.length > 10;
    }

    /**
     * Validate Figma node ID format
     * @param {string} nodeId - Node ID to validate
     * @returns {boolean} - True if valid format
     */
    isValidNodeId(nodeId) {
        const regex = /^I?\d+[:|-]\d+(?:;\d+[:|-]\d+)*$/;
        return regex.test(nodeId);
    }

    /**
     * Generate asset filename from node data
     * @param {Object} nodeData - Node data from Figma API
     * @param {string} extension - File extension (svg, png, etc.)
     * @returns {string} - Generated filename
     */
    generateAssetFilename(nodeData, extension = 'svg') {
        const name = nodeData.name || 'asset';
        const sanitized = name
            .toLowerCase()
            .replace(/[^a-z0-9]/g, '-')
            .replace(/-+/g, '-')
            .replace(/^-|-$/g, '');
        
        const nodeId = nodeData.id.replace(':', '-');
        return `${sanitized}-${nodeId}.${extension}`;
    }

    /**
     * Parse design tokens from Figma styles
     * @param {Object} figmaData - Complete Figma file data
     * @returns {Object} - Parsed design tokens
     */
    parseDesignTokens(figmaData) {
        const tokens = {
            colors: {},
            typography: {},
            spacing: {},
            shadows: {},
            borderRadius: {}
        };

        try {
            // Parse color styles
            if (figmaData.styles) {
                Object.values(figmaData.styles).forEach(style => {
                    if (style.styleType === 'FILL') {
                        tokens.colors[style.name] = this.extractColorValue(style);
                    } else if (style.styleType === 'TEXT') {
                        tokens.typography[style.name] = this.extractTextStyle(style);
                    } else if (style.styleType === 'EFFECT') {
                        tokens.shadows[style.name] = this.extractEffectStyle(style);
                    }
                });
            }

            // Parse component spacing and border radius
            if (figmaData.document) {
                this.parseNodeProperties(figmaData.document, tokens);
            }

        } catch (error) {
            console.error('Error parsing design tokens:', error);
        }

        return tokens;
    }

    /**
     * Extract color value from Figma style
     * @param {Object} style - Figma color style
     * @returns {string} - CSS color value
     */
    extractColorValue(style) {
        try {
            if (style.fills && style.fills[0]) {
                const fill = style.fills[0];
                if (fill.type === 'SOLID') {
                    const { r, g, b } = fill.color;
                    const alpha = fill.opacity || 1;
                    
                    if (alpha < 1) {
                        return `rgba(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(b * 255)}, ${alpha})`;
                    } else {
                        return `rgb(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(b * 255)})`;
                    }
                }
            }
        } catch (error) {
            console.error('Error extracting color value:', error);
        }
        return '#000000';
    }

    /**
     * Extract text style properties
     * @param {Object} style - Figma text style
     * @returns {Object} - CSS text properties
     */
    extractTextStyle(style) {
        try {
            const textStyle = style.style || {};
            return {
                fontFamily: textStyle.fontFamily || 'Inter',
                fontSize: `${textStyle.fontSize || 16}px`,
                fontWeight: textStyle.fontWeight || 400,
                lineHeight: textStyle.lineHeightPx ? `${textStyle.lineHeightPx}px` : 'normal',
                letterSpacing: textStyle.letterSpacing ? `${textStyle.letterSpacing}px` : 'normal'
            };
        } catch (error) {
            console.error('Error extracting text style:', error);
            return {};
        }
    }

    /**
     * Extract effect style (shadows, blurs)
     * @param {Object} style - Figma effect style
     * @returns {string} - CSS box-shadow value
     */
    extractEffectStyle(style) {
        try {
            if (style.effects && style.effects[0]) {
                const effect = style.effects[0];
                if (effect.type === 'DROP_SHADOW') {
                    const { x, y, blur, spread } = effect.offset;
                    const color = this.extractColorValue({ fills: [{ color: effect.color, opacity: effect.color.a }] });
                    return `${x}px ${y}px ${blur}px ${spread || 0}px ${color}`;
                }
            }
        } catch (error) {
            console.error('Error extracting effect style:', error);
        }
        return 'none';
    }

    /**
     * Parse node properties for spacing and border radius
     * @param {Object} node - Figma node
     * @param {Object} tokens - Tokens object to populate
     */
    parseNodeProperties(node, tokens) {
        try {
            // Extract border radius
            if (node.cornerRadius !== undefined) {
                tokens.borderRadius[`radius-${node.cornerRadius}`] = `${node.cornerRadius}px`;
            }

            // Extract padding/spacing
            if (node.paddingLeft !== undefined) {
                tokens.spacing[`padding-${node.paddingLeft}`] = `${node.paddingLeft}px`;
            }

            // Recursively parse children
            if (node.children) {
                node.children.forEach(child => this.parseNodeProperties(child, tokens));
            }
        } catch (error) {
            console.error('Error parsing node properties:', error);
        }
    }

    /**
     * Generate CSS variables from design tokens
     * @param {Object} tokens - Design tokens object
     * @returns {string} - CSS variables string
     */
    generateCSSVariables(tokens) {
        let css = ':root {\n';

        // Colors
        Object.entries(tokens.colors).forEach(([name, value]) => {
            const varName = name.toLowerCase().replace(/\s+/g, '-');
            css += `  --color-${varName}: ${value};\n`;
        });

        // Typography
        Object.entries(tokens.typography).forEach(([name, style]) => {
            const varName = name.toLowerCase().replace(/\s+/g, '-');
            css += `  --font-${varName}-family: ${style.fontFamily};\n`;
            css += `  --font-${varName}-size: ${style.fontSize};\n`;
            css += `  --font-${varName}-weight: ${style.fontWeight};\n`;
            css += `  --font-${varName}-line-height: ${style.lineHeight};\n`;
        });

        // Spacing
        Object.entries(tokens.spacing).forEach(([name, value]) => {
            css += `  --space-${name}: ${value};\n`;
        });

        // Shadows
        Object.entries(tokens.shadows).forEach(([name, value]) => {
            const varName = name.toLowerCase().replace(/\s+/g, '-');
            css += `  --shadow-${varName}: ${value};\n`;
        });

        // Border Radius
        Object.entries(tokens.borderRadius).forEach(([name, value]) => {
            css += `  --${name}: ${value};\n`;
        });

        css += '}\n';
        return css;
    }

    /**
     * Log API operation for debugging
     * @param {string} operation - Operation name
     * @param {Object} params - Operation parameters
     * @param {Object} result - Operation result
     */
    logOperation(operation, params, result) {
        const logEntry = {
            timestamp: new Date().toISOString(),
            operation,
            params,
            success: !result.error,
            error: result.error || null
        };

        console.log('Figma API Operation:', logEntry);
        
        // Store in localStorage for debugging
        try {
            const logs = JSON.parse(localStorage.getItem('figma-api-logs') || '[]');
            logs.push(logEntry);
            // Keep only last 100 logs
            if (logs.length > 100) {
                logs.splice(0, logs.length - 100);
            }
            localStorage.setItem('figma-api-logs', JSON.stringify(logs));
        } catch (error) {
            console.warn('Could not store API log:', error);
        }
    }

    /**
     * Get stored API logs for debugging
     * @returns {Array} - Array of log entries
     */
    getApiLogs() {
        try {
            return JSON.parse(localStorage.getItem('figma-api-logs') || '[]');
        } catch (error) {
            console.error('Error retrieving API logs:', error);
            return [];
        }
    }

    /**
     * Clear stored API logs
     */
    clearApiLogs() {
        try {
            localStorage.removeItem('figma-api-logs');
            console.log('API logs cleared');
        } catch (error) {
            console.error('Error clearing API logs:', error);
        }
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = FigmaUtils;
} else {
    window.FigmaUtils = FigmaUtils;
}