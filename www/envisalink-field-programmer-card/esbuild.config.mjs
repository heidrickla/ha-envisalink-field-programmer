import * as esbuild from "esbuild";

const watch = process.argv.includes("--watch");

// The build output goes straight into the custom_components tree, not a
// local dist/ folder: HACS only ships custom_components/<domain>/ to users,
// so that's the only place a bundled frontend asset can live and still be
// installed alongside the integration. This folder is a dev workspace only.
const options = {
  entryPoints: ["src/envisalink-field-programmer-card.ts"],
  bundle: true,
  outfile:
    "../../custom_components/envisalink_field_programmer/www/envisalink-field-programmer-card.js",
  format: "esm",
  target: "es2021",
  minify: !watch,
  sourcemap: watch,
  legalComments: "none",
};

if (watch) {
  const ctx = await esbuild.context(options);
  await ctx.watch();
  console.log("Watching for changes...");
} else {
  await esbuild.build(options);
  console.log("Built envisalink-field-programmer-card.js");
}
