import { stitch } from "@google/stitch-sdk";
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const projectId = "4039997107921041740";
const screenId = "83b61295a50a4c049fef62640b5e3254";

if (!process.env.STITCH_API_KEY && !process.env.STITCH_ACCESS_TOKEN) {
  console.error(
    "Missing Stitch auth. Set STITCH_API_KEY (recommended) or STITCH_ACCESS_TOKEN (+ GOOGLE_CLOUD_PROJECT).",
  );
  process.exit(1);
}

const outDir = path.resolve(
  process.cwd(),
  "..",
  "stitch_drug_discovery_research_agent",
  "login_chemsynth_ai",
  "downloads",
);
fs.mkdirSync(outDir, { recursive: true });

const project = stitch.project(projectId);
const screen = await project.getScreen(screenId);

const htmlUrl = await screen.getHtml();
const imageUrl = await screen.getImage();

console.log("Resolved hosted URLs:");
console.log("HTML:", htmlUrl);
console.log("IMAGE:", imageUrl);

const htmlPath = path.join(outDir, "code.html");
const imagePath = path.join(outDir, "screenshot.png");

console.log("\nDownloading with curl -L ...");
execSync(`curl -L "${htmlUrl}" -o "${htmlPath}"`, { stdio: "inherit" });
execSync(`curl -L "${imageUrl}" -o "${imagePath}"`, { stdio: "inherit" });

console.log("\nSaved:");
console.log(htmlPath);
console.log(imagePath);
