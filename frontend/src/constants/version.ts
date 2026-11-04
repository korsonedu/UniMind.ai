declare const __APP_VERSION__: string;
declare const __APP_BUILD__: string;

// build 时由 vite.config.ts 从 frontend/package.json 注入产品版本。
export const APP_VERSION: string = __APP_VERSION__;
export const APP_BUILD: string = __APP_BUILD__;
export const COPYRIGHT_YEAR = "2019-2026";
export const COPYRIGHT_ENTITY = "北京融知高科 · UniMind.ai";
export const BRAND_DESC = "AGENT-DRIVEN EDUCATION PLATFORM";
