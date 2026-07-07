// @ts-check
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

// The live simulator (the FastAPI workbench), served on its custom domain.
// (The Fly app is still reachable at antennaknobs.fly.dev, but app.antennaknobs.dev
// is the canonical public URL.) Referenced from the home hero and the Web docs.
const SIMULATOR_URL = "https://app.antennaknobs.dev/";

// https://astro.build/config
export default defineConfig({
  site: "https://antennaknobs.dev",
  integrations: [
    starlight({
      title: "AntennaKNoBs",
      tagline: "Turn a knob, watch the antenna.",
      social: [
        {
          icon: "github",
          label: "GitHub",
          href: "https://github.com/stevenmburns/antennaknobs",
        },
      ],
      customCss: ["./src/styles/custom.css"],
      // Load IBM Plex Sans / Mono (the app's typefaces) — same source as the
      // app's index.html. custom.css points --sl-font / --sl-font-mono at them.
      head: [
        {
          tag: "link",
          attrs: { rel: "preconnect", href: "https://fonts.googleapis.com" },
        },
        {
          tag: "link",
          attrs: {
            rel: "preconnect",
            href: "https://fonts.gstatic.com",
            crossorigin: true,
          },
        },
        {
          tag: "link",
          attrs: {
            rel: "stylesheet",
            href: "https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap",
          },
        },
        // Cloudflare Web Analytics beacon. The apex zones antennaknobs.dev and
        // antennaknobs.com serve this one docs build, so a single token rolls
        // both domains' traffic into one dashboard. The token is a public
        // client-side id (ships in every page), not a secret. It lives here in
        // the site <head> — rather than being auto-injected by Cloudflare —
        // because the Fly DNS records are grey-cloud (DNS-only, required for
        // Fly's TLS/SNI routing), so CF never proxies the request to inject it.
        {
          tag: "script",
          attrs: {
            defer: true,
            src: "https://static.cloudflareinsights.com/beacon.min.js",
            "data-cf-beacon": '{"token": "a7ed2b6512b5461fbd0beac3d6e13d71"}',
          },
        },
      ],
      sidebar: [
        {
          label: "Start here",
          items: [
            { label: "What is antennaknobs?", slug: "start/welcome" },
            { label: "Quickstart", slug: "start/quickstart" },
            { label: "Open the live simulator", link: SIMULATOR_URL, attrs: { target: "_blank" } },
          ],
        },
        {
          label: "Concepts",
          items: [
            { label: "The model", slug: "concepts/model" },
            { label: "Write your first design", slug: "concepts/first-builder" },
            { label: "Many ways to express geometry", slug: "concepts/authoring" },
            {
              label: "Writing designs with Claude Code",
              slug: "concepts/authoring-with-claude",
            },
          ],
        },
        {
          label: "Reference",
          items: [
            { label: "Design catalog", slug: "reference/catalog" },
            { label: "The solver & accuracy", slug: "reference/solver" },
            { label: "Web workbench", slug: "reference/web" },
            { label: "Drone & Transform API", slug: "reference/drone-transform" },
            { label: "Command line", slug: "reference/cli" },
            { label: "Release notes", slug: "reference/releases" },
          ],
        },
        {
          label: "Project",
          items: [{ label: "Contributing", slug: "project/contributing" }],
        },
      ],
    }),
  ],
});
