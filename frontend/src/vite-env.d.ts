/// <reference types="vite/client" />

// Номер релиза, «вшитый» в сборку (см. vite.config.ts и frontend/Dockerfile.prod:
// ARG APP_VERSION). В проде это git-тег релиза (напр. «v1.1.8»), локально/в dev — «dev».
declare const __APP_VERSION__: string;
