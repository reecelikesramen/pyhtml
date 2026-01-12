import * as esbuild from 'esbuild';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

const isDev = process.argv.includes('--dev');
const isWatch = process.argv.includes('--watch');

const buildOptions = {
    entryPoints: [resolve(__dirname, 'src/index.ts')],
    bundle: true,
    outfile: resolve(__dirname, '../static/pyhtml.min.js'),
    format: 'iife',
    globalName: 'PyHTML',
    target: ['es2020'],
    minify: !isDev,
    sourcemap: isDev,
    treeShaking: true,
    define: {
        'process.env.NODE_ENV': isDev ? '"development"' : '"production"'
    },
    banner: {
        js: '/* PyHTML Client v0.0.1 - https://github.com/reecelikesramen/pyhtml */'
    }
};

async function build() {
    try {
        if (isWatch) {
            const ctx = await esbuild.context(buildOptions);
            await ctx.watch();
            console.log('Watching for changes...');
        } else {
            const result = await esbuild.build(buildOptions);
            console.log('Build complete!');
            if (result.metafile) {
                console.log(await esbuild.analyzeMetafile(result.metafile));
            }
        }
    } catch (err) {
        console.error('Build failed:', err);
        process.exit(1);
    }
}

build();
