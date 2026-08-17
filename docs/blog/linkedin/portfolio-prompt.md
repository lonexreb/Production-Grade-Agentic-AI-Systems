# Prompt for the portfolio-website repo

Paste everything below into a Claude Code session running in the portfolio repo.

---

Add a new blog post to my portfolio site from a pre-built, self-contained HTML page.

**Source:** download the article HTML from
https://raw.githubusercontent.com/lonexreb/Production-Grade-Agentic-AI-Systems/main/docs/showcase/three-failures-blog.html

**About the file (important constraints):**
- It is fully self-contained: all CSS is inline in a `<style>` block, and the three
  terminal-recording GIFs are embedded as base64 data URIs (~280 KB total). It has
  no external dependencies, no JavaScript, and no `<html>/<head>/<body>` wrapper —
  it's body content plus a `<meta charset>`, `<title>`, and one `<style>` block.
- It is theme-aware: it defines its palette on `:root` (light) with a
  `prefers-color-scheme: dark` override and `[data-theme]` overrides. If my site
  sets a `data-theme` attribute on `<html>`, it will adapt automatically.
- Do NOT rewrite, summarize, or restyle the article content — the design (dark
  ops-room aesthetic, red/green scoreboards, amber callouts) is intentional and
  should render exactly as-is inside the post body.

**Task:**
1. Detect this site's stack and blog conventions (framework, where posts live, how
   the index/nav lists them) and follow them.
2. Integrate the article as a blog post titled "Three Real Agent Failures,
   Replayed" (slug: `three-real-agent-failures`), dated 2026-08-17, with
   description: "Three failures real developers reported publicly — reproduced as
   runnable code, then fixed with boring runtime primitives. With live terminal
   recordings." Choose the least-risky integration for this stack:
   - If posts are MDX/JSX: render the fetched HTML via the framework's raw-HTML
     mechanism (e.g. `dangerouslySetInnerHTML` from an imported .html string, or
     Astro's `set:html`) inside the site's standard blog layout shell.
   - If that risks CSS collisions with the site's global styles, instead copy the
     file to the static/public directory as a standalone page and make the blog
     index entry link to it — correctness over cleverness.
   - Namespace/scope the article's CSS only if a real collision shows up in
     verification; otherwise leave it untouched.
3. Add proper page metadata: `<title>`, meta description, and Open Graph/Twitter
   card tags (og:title, og:description, og:type=article). For the og:image,
   extract the first frame of the first embedded GIF to a static PNG if the stack
   makes that easy; otherwise skip the image rather than hack it.
4. Add the post to the blog index / homepage listing following existing patterns
   exactly (same component, same date formatting).
5. At the end of the article page, add a small footer line in the site's own
   style: "Part of the OpenAgentOS series —" linking to
   https://github.com/lonexreb/Production-Grade-Agentic-AI-Systems
6. Verify before finishing: run the site's dev server or build, open the new post,
   and confirm (a) the page renders with the article's own dark styling intact,
   (b) all three GIFs animate, (c) nothing on the rest of the site changed
   visually, (d) the build passes. Screenshot the rendered post.
7. Commit with a conventional message, but do NOT push or deploy — show me the
   rendered result and the diff summary first.
