/**
 * Get Nexus-Stack version from GitHub releases
 * GET /api/version
 *
 * Returns the latest release version from GitHub.
 *
 * Deliberately NOT identity-guarded, unlike the other GETs here. Header
 * .astro fetches it on every page render, including for an Access
 * identity that is on the whitelist but is neither the admin nor in
 * USER_EMAIL, and what it returns is a public GitHub release tag plus the
 * owner/repo already printed in this repository's README. The hostname
 * check in functions/_middleware.js still applies.
 */
import {
  forgeErrorMessage, forgeErrorStatus, forgeFetch, forgeHeaders, repoApiUrl, repoWebUrl,
} from './_utils/forge.js';

export async function onRequestGet(context) {
  const { env } = context;

  // Prefer the explicit deployed-version env var if it's set. This is the
  // authoritative source for user-fork deployments: the admin panel writes
  // the template release tag (e.g. `v0.51.1`) into the fork on every
  // Setup / Upgrade, and the setup-control-plane workflow pushes it into
  // the Pages project as the TEMPLATE_VERSION secret. GitHub's
  // releases-latest endpoint on a fork returns 404 (forks don't inherit
  // releases), which used to leave the UI labelled "dev" for every
  // multi-tenant user regardless of which version they were actually on.
  if (env.TEMPLATE_VERSION && env.TEMPLATE_VERSION.trim()) {
    const tag = env.TEMPLATE_VERSION.trim();
    return new Response(JSON.stringify({
      success: true,
      version: tag,
      name: tag,
      url: `https://github.com/stefanko-ch/Nexus-Stack/releases/tag/${tag}`,
      publishedAt: null,
      source: 'env',
    }), {
      headers: {
        'Content-Type': 'application/json',
        'Cache-Control': 'public, max-age=300',
      },
    });
  }

  // Validate environment variables
  const missing = [];
  if (!env.GITHUB_TOKEN) missing.push('GITHUB_TOKEN');
  if (!env.GITHUB_OWNER) missing.push('GITHUB_OWNER');
  if (!env.GITHUB_REPO) missing.push('GITHUB_REPO');

  if (missing.length > 0) {
    return new Response(JSON.stringify({
      success: false,
      error: `Missing required environment variables: ${missing.join(', ')}`
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  try {
    // Fetch the latest release from GitHub
    const url = repoApiUrl(env, '/releases/latest');

    const response = await forgeFetch(env, url, { headers: forgeHeaders(env) });

    if (!response.ok) {
      // If no releases exist yet, return a default version
      if (response.status === 404) {
        return new Response(JSON.stringify({
          success: true,
          version: 'dev',
          name: 'Development',
          url: repoWebUrl(env),
          publishedAt: null,
        }), {
          headers: {
            'Content-Type': 'application/json',
            'Cache-Control': 'public, max-age=300', // 300s = 5 minutes
          },
        });
      }

      console.error(`Releases API error: ${response.status}`);

      return new Response(JSON.stringify({
        success: false,
        error: await forgeErrorMessage(response, 'Failed to fetch version')
      }), {
        status: forgeErrorStatus(response),
        headers: { 'Content-Type': 'application/json' },
      });
    }

    const release = await response.json();

    return new Response(JSON.stringify({
      success: true,
      version: release.tag_name,
      name: release.name || release.tag_name,
      url: release.html_url,
      publishedAt: release.published_at,
    }), {
      headers: {
        'Content-Type': 'application/json',
        'Cache-Control': 'public, max-age=300', // 300s = 5 minutes
      },
    });
  } catch (error) {
    console.error('Version endpoint error:', error);
    return new Response(JSON.stringify({
      success: false,
      error: 'Internal server error'
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
