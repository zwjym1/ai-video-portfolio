import { Config } from "@remotion/cli/config";
// 盒上无 GPU：用 swangle（SwiftShader），已在 ep01 v9 试片验证可渲染
Config.setVideoImageFormat("jpeg");
Config.setJpegQuality(93);
Config.setChromiumOpenGlRenderer("swangle");
