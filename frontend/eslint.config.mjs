import { defineConfig, globalIgnores } from "eslint/config";
import tseslint from "typescript-eslint";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import jsxA11y from "eslint-plugin-jsx-a11y";
import importPlugin from "eslint-plugin-import";
import globals from "globals";

// The upstream Next ESLint plugin currently pulls the unpatched braces advisory
// through fast-glob. Keep the App Router checks relevant here in a local plugin.
const nextBoundary = {
  rules: {
    "app-router-elements": {
      meta: { type: "problem" },
      create(context) {
        return {
          JSXOpeningElement(node) {
            const tag = node.name.type === "JSXIdentifier" ? node.name.name : null;
            if (tag === "head") {
              context.report({ node, message: "Use the Next metadata API instead of a raw head element." });
            }
            if (tag === "img") {
              context.report({ node, message: "Use next/image for optimized images." });
            }
            if (tag === "script") {
              context.report({ node, message: "Use next/script for script loading." });
            }
            if (tag === "a") {
              const href = node.attributes.find(
                (attribute) => attribute.type === "JSXAttribute" && attribute.name.name === "href",
              );
              if (href?.value?.type === "Literal" && /^\/(?!\/|api\/)/.test(href.value.value)) {
                context.report({ node, message: "Use next/link for internal navigation." });
              }
            }
          },
        };
      },
    },
    "no-async-client-component": {
      meta: { type: "problem" },
      create(context) {
        const source = context.sourceCode.ast;
        const isClient = source.body[0]?.type === "ExpressionStatement" &&
          source.body[0].expression?.value === "use client";
        if (!isClient) return {};
        function check(node) {
          if (node.async && /^[A-Z]/.test(node.id?.name ?? "")) {
            context.report({ node, message: "Client Components cannot be async." });
          }
        }
        return {
          FunctionDeclaration: check,
          VariableDeclarator(node) {
            if (node.init?.async && /^[A-Z]/.test(node.id?.name ?? "")) {
              context.report({ node, message: "Client Components cannot be async." });
            }
          },
        };
      },
    },
  },
};

export default defineConfig([
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{js,jsx,mjs,ts,tsx,mts,cts}"],
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    plugins: {
      react,
      "react-hooks": reactHooks,
      "jsx-a11y": jsxA11y,
      import: importPlugin,
      "verity-next": nextBoundary,
    },
    settings: { react: { version: "detect" } },
    rules: {
      ...react.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      ...jsxA11y.configs.recommended.rules,
      "react/react-in-jsx-scope": "off",
      "react/prop-types": "off",
      "react/no-unknown-property": "off",
      // The MFA challenge intentionally focuses its code field when revealed.
      "jsx-a11y/no-autofocus": "off",
      "jsx-a11y/label-has-associated-control": ["error", { assert: "either", depth: 5 }],
      // The live conversation log is keyboard-scrollable by design.
      "jsx-a11y/no-noninteractive-tabindex": ["error", { roles: ["log"] }],
      "@typescript-eslint/no-unused-vars": "warn",
      "@typescript-eslint/no-unused-expressions": "warn",
      "import/no-anonymous-default-export": "warn",
      "verity-next/app-router-elements": "error",
      "verity-next/no-async-client-component": "error",
      "no-restricted-imports": ["error", { paths: ["next/document"] }],
    },
  },
  globalIgnores([".next/**", "out/**", "build/**", "node_modules/**", "playwright-report/**", "next-env.d.ts"]),
]);
