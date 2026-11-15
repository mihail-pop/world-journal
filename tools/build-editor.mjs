import { build } from "esbuild";
import { readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";

const result = await build({
    entryPoints: ["tools/editor-vendor.js"],
    outfile: "static/vendor/tiptap/editor.js",
    bundle: true,
    format: "esm",
    target: "es2020",
    minify: true,
    legalComments: "linked",
    metafile: true,
});

const packages = new Set();
for (const input of Object.keys(result.metafile.inputs)) {
    const match = input.replaceAll("\\", "/").match(/^(.*node_modules\/(?:@[^/]+\/)?[^/]+)\//);
    if (match) packages.add(match[1]);
}
const licenses = [];
for (const path of [...packages].sort()) {
    const metadata = JSON.parse(await readFile(join(path, "package.json"), "utf8"));
    let license;
    for (const filename of ["LICENSE", "LICENSE.md", "LICENSE.txt", "license", "license.txt"]) {
        try { license = await readFile(join(path, filename), "utf8"); break; } catch {}
    }
    if (!license) throw new Error(`Missing license for ${metadata.name}`);
    licenses.push(`${metadata.name} ${metadata.version}\n${license.trim()}`);
}
await writeFile(join(dirname("static/vendor/tiptap/editor.js"), "LICENSES.txt"), licenses.join("\n\n--------------------\n\n") + "\n");
