import * as esbuild from 'esbuild';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

const isDev = process.argv.includes('--dev');
const isWatch = process.argv.includes('--watch');

// Bundle configurations
const bundles = [
    {
        name: 'core',
        entryPoints: [resolve(__dirname, 'src/pyhtml.core.ts')],
        outfile: resolve(__dirname, '../static/pyhtml.core.min.js'),
        globalName: 'PyHTMLCore'
    },
    {
        name: 'dev',
        entryPoints: [resolve(__dirname, 'src/pyhtml.dev.ts')],
        outfile: resolve(__dirname, '../static/pyhtml.dev.min.js'),
        globalName: 'PyHTML'
    }
];

function getBuildOptions(bundle) {
    return {
        entryPoints: bundle.entryPoints,
        bundle: true,
        outfile: bundle.outfile,
        format: 'iife',
        globalName: bundle.globalName,
        target: ['es2020'],
        minify: !isDev,
        sourcemap: isDev,
        treeShaking: true,
        define: {
            'process.env.NODE_ENV': isDev ? '"development"' : '"production"'
        },
        banner: {
            js: `/* PyHTML Client ${bundle.name} v0.0.1 - https://github.com/reecelikesramen/pyhtml */`
        }
    };
}

async function build() {
    try {
        if (isWatch) {
            // Build all bundles initially, then watch dev bundle
            for (const bundle of bundles) {
                await esbuild.build(getBuildOptions(bundle));
                console.log(`Built ${bundle.name} bundle`);
            }

            // Watch dev bundle for changes
            const ctx = await esbuild.context(getBuildOptions(bundles[1]));
            await ctx.watch();
            console.log('Watching dev bundle for changes...');
        } else {
            // Build all bundles
            for (const bundle of bundles) {
                const result = await esbuild.build(getBuildOptions(bundle));
                console.log(`Built ${bundle.name}: ${bundle.outfile}`);
            }
            console.log('Build complete!');
        }
    } catch (err) {
        console.error('Build failed:', err);
        process.exit(1);
    }
}

build();
