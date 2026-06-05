import nextVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

const eslintConfig = [
  ...nextVitals,
  ...nextTypescript,
  {
    ignores: [
      ".next/**",
      "out/**",
      "build/**",
      "dist/**",
      "coverage/**",
      "next-env.d.ts",
      "tsconfig.tsbuildinfo",
      "playwright-report/**",
      "test-results/**",
    ],
  },
];

export default eslintConfig;
