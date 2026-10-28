// Copy the Python backend into the extension so the packaged .vsix is
// self-contained. The repo keeps one source of truth in ../; py/ is a snapshot.
const fs = require("fs");
const path = require("path");

const src = path.resolve(__dirname, "..", "..");
const dst = path.resolve(__dirname, "..", "py");

fs.rmSync(dst, { recursive: true, force: true });
fs.mkdirSync(dst, { recursive: true });

for (const f of ["server.py", "mdparse.py"]) {
  fs.copyFileSync(path.join(src, f), path.join(dst, f));
}
fs.cpSync(path.join(src, "static"), path.join(dst, "static"), { recursive: true });

console.log(`bundled server.py, mdparse.py, static/ -> ${dst}`);
