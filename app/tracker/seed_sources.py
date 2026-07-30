"""Seed provider/product/source registry - the vendors that actually show
up in real shadow-AI discovery (ChatGPT, Copilot/Azure OpenAI, Claude,
Gemini, ...), not the speculative long tail of inference infra vendors the
original spec also listed. Idempotent upsert keyed by slug. This is a seed,
not a permanent truth - the tracker itself is expected to discover
redirects/renames over time.

URL notes (verified live 2026-07-27, see docs/URL_NOTES.md):
- The two openai.com/index/... blog announcements are dropped: they 403
  specifically against httpx's TLS/HTTP2 fingerprint (confirmed reproducible
  vs. curl succeeding on the identical URL) - working around that would mean
  TLS-impersonation, which is bot-protection bypass and out of scope. The
  developers.openai.com API docs page already covers the same facts at
  higher authority (official_product_documentation vs. official_blog).
- docs.anthropic.com pages are a client-rendered SPA (confirmed: raw fetched
  bytes contain only a "Loading..." placeholder, not an httpx-specific
  issue). Replaced the zero-data-retention page with the equivalent static
  articles on privacy.claude.com (Anthropic's own privacy center, verified
  working). Release notes and supported-regions have no verified working
  static replacement yet - not seeded until browser-rendering fallback
  exists (see Phase 2 notes in memory/residency_tracker.md).

Second expansion (2026-07-27): added 33 more vendors straight from ShadowAI's
own seed_catalog.json (grammarly, notion, the AI meeting-notetaker bots,
GitHub Copilot, code assistants, image/video/voice generators, Microsoft 365
Copilot and Google Workspace Gemini specifically - both distinct products
from the raw APIs already seeded above) - these are the tools that actually
get discovered via OAuth grants, not just the underlying model infra.
Every URL below was verified live (curl, both an honest UA and a browser UA,
checked for real static content vs. a JS shell) before being added - none
were guessed. Skipped: Adobe Firefly - every adobe.com/helpx.adobe.com URL
tried failed to even establish a connection (curl exit 28, reproduced
independently outside the research agent too), which looks like network- or
TLS-layer blocking rather than a simple UA check; revisit from a different
network before seeding it. Also skipped several "Trust Center" URLs that
looked official in search results but turned out to be bare Vanta-hosted JS
shells with no static content (trustcenter.writer.com, trust.you.com,
trust.replit.com) - used each vendor's own domain instead.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.provider import Provider
from app.models.source import Source

# Derives a source_class from the existing authority tagging when a seed
# entry doesn't specify one explicitly - authority already roughly encodes
# page type (see migration 17f81db6cc5a for the same mapping applied to
# rows that predate this field). A seed entry can still set "source_class"
# explicitly to override this default.
_AUTHORITY_TO_SOURCE_CLASS = {
    "official_legal": "legal_notice",
    "contractual": "legal_notice",
    "official_trust_center": "trust_center",
    "official_release_notes": "changelog",
}


def _infer_source_class(authority: str) -> str:
    return _AUTHORITY_TO_SOURCE_CLASS.get(authority, "other")


SEED_REGISTRY: list[dict] = [
    {
        "slug": "openai",
        "display_name": "OpenAI",
        "website_url": "https://openai.com",
        "products": [
            {
                "slug": "api-platform",
                "display_name": "OpenAI API Platform",
                "product_type": "direct_api",
                "sources": [
                    {
                        "source_key": "openai-api-data-controls",
                        "canonical_url": "https://developers.openai.com/api/docs/guides/your-data",
                        "authority": "official_product_documentation",
                    },
                ],
            }
        ],
    },
    {
        "slug": "anthropic",
        "display_name": "Anthropic",
        "website_url": "https://anthropic.com",
        "products": [
            {
                "slug": "claude-api",
                "display_name": "Claude first-party API",
                "product_type": "direct_api",
                "sources": [
                    {
                        "source_key": "anthropic-privacy-retention-duration",
                        "canonical_url": "https://privacy.claude.com/en/articles/10023548-how-long-do-you-store-my-data",
                        "authority": "official_trust_center",
                    },
                    {
                        "source_key": "anthropic-privacy-org-retention",
                        "canonical_url": "https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data",
                        "authority": "official_trust_center",
                    },
                ],
            }
        ],
    },
    {
        "slug": "microsoft-azure-openai",
        "display_name": "Microsoft Azure OpenAI / Foundry",
        "website_url": "https://azure.microsoft.com",
        "products": [
            {
                "slug": "foundry-models",
                "display_name": "Microsoft Foundry Models sold by Azure",
                "product_type": "cloud_hosted",
                "sources": [
                    {
                        "source_key": "azure-openai-data-privacy",
                        "canonical_url": "https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/openai/data-privacy",
                        "authority": "official_product_documentation",
                    },
                    {
                        "source_key": "azure-openai-deployment-types",
                        "canonical_url": "https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/deployment-types",
                        "authority": "official_product_documentation",
                    },
                    {
                        "source_key": "azure-openai-region-availability",
                        "canonical_url": "https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure-region-availability",
                        "authority": "official_product_documentation",
                    },
                ],
            }
        ],
    },
    {
        "slug": "aws-bedrock",
        "display_name": "Amazon Bedrock",
        "website_url": "https://aws.amazon.com/bedrock/",
        "products": [
            {
                "slug": "bedrock",
                "display_name": "Amazon Bedrock",
                "product_type": "cloud_hosted",
                "sources": [
                    {
                        "source_key": "bedrock-regional-availability",
                        "canonical_url": "https://docs.aws.amazon.com/bedrock/latest/userguide/models-region-compatibility.html",
                        "authority": "official_product_documentation",
                    },
                    {
                        "source_key": "bedrock-data-protection",
                        "canonical_url": "https://docs.aws.amazon.com/bedrock/latest/userguide/data-protection.html",
                        "authority": "official_product_documentation",
                    },
                    {
                        "source_key": "bedrock-inference-profiles",
                        "canonical_url": "https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-support.html",
                        "authority": "official_product_documentation",
                    },
                ],
            }
        ],
    },
    {
        "slug": "google-cloud-genai",
        "display_name": "Google Cloud generative AI",
        "website_url": "https://cloud.google.com",
        "products": [
            {
                "slug": "gemini-developer-api",
                "display_name": "Gemini Developer API",
                "product_type": "direct_api",
                "sources": [
                    {
                        "source_key": "gemini-api-available-regions",
                        "canonical_url": "https://ai.google.dev/gemini-api/docs/available-regions",
                        "authority": "official_product_documentation",
                    },
                ],
            },
            {
                "slug": "gemini-enterprise-agent-platform",
                "display_name": "Gemini Enterprise Agent Platform",
                "product_type": "cloud_hosted",
                "sources": [
                    {
                        "source_key": "gemini-enterprise-data-residency",
                        "canonical_url": "https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/data-residency",
                        "authority": "official_product_documentation",
                    },
                    {
                        "source_key": "gemini-enterprise-zero-retention",
                        "canonical_url": "https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/zero-data-retention",
                        "authority": "official_product_documentation",
                    },
                ],
            },
        ],
    },
    {
        "slug": "mistral",
        "display_name": "Mistral AI",
        "website_url": "https://mistral.ai",
        "products": [
            {
                "slug": "hosted-api",
                "display_name": "Mistral hosted API",
                "product_type": "direct_api",
                "sources": [
                    {
                        "source_key": "mistral-data-location",
                        "canonical_url": "https://help.mistral.ai/en/articles/347629-where-do-you-store-my-data-or-my-organization-s-data",
                        "authority": "official_support",
                    },
                    {
                        "source_key": "mistral-legal-terms",
                        "canonical_url": "https://legal.mistral.ai/terms",
                        "authority": "official_legal",
                    },
                ],
            }
        ],
    },
    {
        "slug": "cohere",
        "display_name": "Cohere",
        "website_url": "https://cohere.com",
        "products": [
            {
                "slug": "saas-api",
                "display_name": "Cohere SaaS API",
                "product_type": "direct_api",
                "sources": [
                    {
                        "source_key": "cohere-security",
                        "canonical_url": "https://cohere.com/security",
                        "authority": "official_product_documentation",
                    },
                    {
                        "source_key": "cohere-deployment-options",
                        "canonical_url": "https://cohere.com/deployment-options",
                        "authority": "official_product_documentation",
                    },
                ],
            }
        ],
    },
    # --- Second expansion: tools that actually get discovered via OAuth
    # grants, not just underlying model-infra providers. See module
    # docstring for URL-verification notes. ---
    {
        "slug": "perplexity",
        "display_name": "Perplexity AI",
        "website_url": "https://www.perplexity.ai",
        "products": [
            {
                "slug": "perplexity-ai",
                "display_name": "Perplexity",
                "product_type": "ai_search_saas",
                "sources": [
                    {
                        # perplexity.ai blocks httpx's TLS/HTTP2 fingerprint
                        # site-wide (confirmed on multiple pages incl. root -
                        # not just this one URL); disabled rather than left
                        # to fail forever. Re-enable if a working alternate
                        # domain/page is found, or from a different network.
                        "source_key": "perplexity-retention-privacy",
                        "canonical_url": "https://www.perplexity.ai/help-center/en/articles/11187708-data-retention-and-privacy-for-enterprise-organizations-and-users",
                        "authority": "official_support",
                        "enabled": False,
                    },
                ],
            }
        ],
    },
    {
        "slug": "jasper",
        "display_name": "Jasper AI",
        "website_url": "https://www.jasper.ai",
        "products": [
            {
                "slug": "jasper-ai",
                "display_name": "Jasper",
                "product_type": "ai_writing_saas",
                "sources": [
                    {
                        "source_key": "jasper-trust",
                        "canonical_url": "https://www.jasper.ai/trust",
                        "authority": "official_trust_center",
                    },
                ],
            }
        ],
    },
    {
        "slug": "grammarly",
        "display_name": "Grammarly",
        "website_url": "https://www.grammarly.com",
        "products": [
            {
                "slug": "grammarly",
                "display_name": "Grammarly",
                "product_type": "writing_assistant_saas",
                "sources": [
                    {
                        "source_key": "grammarly-trust",
                        "canonical_url": "https://www.grammarly.com/trust",
                        "authority": "official_trust_center",
                    },
                ],
            }
        ],
    },
    {
        "slug": "notion",
        "display_name": "Notion",
        "website_url": "https://www.notion.com",
        "products": [
            {
                "slug": "notion-ai",
                "display_name": "Notion AI",
                "product_type": "productivity_ai_saas",
                "sources": [
                    {
                        "source_key": "notion-ai-security",
                        "canonical_url": "https://www.notion.com/help/notion-ai-security-practices",
                        "authority": "official_support",
                    },
                ],
            }
        ],
    },
    {
        "slug": "otter-ai",
        "display_name": "Otter.ai",
        "website_url": "https://otter.ai",
        "products": [
            {
                "slug": "otter-ai",
                "display_name": "Otter.ai",
                "product_type": "meeting_notetaker_saas",
                "sources": [
                    {
                        "source_key": "otter-privacy-policy",
                        "canonical_url": "https://otter.ai/privacy-policy",
                        "authority": "official_legal",
                    },
                ],
            }
        ],
    },
    {
        "slug": "fireflies-ai",
        "display_name": "Fireflies.ai",
        "website_url": "https://fireflies.ai",
        "products": [
            {
                "slug": "fireflies-ai",
                "display_name": "Fireflies.ai",
                "product_type": "meeting_notetaker_saas",
                "sources": [
                    {
                        "source_key": "fireflies-security",
                        "canonical_url": "https://fireflies.ai/security",
                        "authority": "official_trust_center",
                    },
                ],
            }
        ],
    },
    {
        "slug": "fathom",
        "display_name": "Fathom",
        "website_url": "https://www.fathom.ai",
        "products": [
            {
                "slug": "fathom",
                "display_name": "Fathom",
                "product_type": "meeting_notetaker_saas",
                "sources": [
                    {
                        # Domain migrated fathom.video -> fathom.ai (confirmed
                        # via 301 redirect + matching product content).
                        # ShadowAI's own catalog still lists fathom.video -
                        # worth updating there too, separately.
                        "source_key": "fathom-privacy",
                        "canonical_url": "https://www.fathom.ai/privacy",
                        "authority": "official_legal",
                    },
                ],
            }
        ],
    },
    {
        "slug": "grain",
        "display_name": "Grain",
        "website_url": "https://grain.com",
        "products": [
            {
                "slug": "grain",
                "display_name": "Grain",
                "product_type": "meeting_notetaker_saas",
                "sources": [
                    {
                        "source_key": "grain-security",
                        "canonical_url": "https://grain.com/security",
                        "authority": "official_trust_center",
                    },
                ],
            }
        ],
    },
    {
        "slug": "tldv",
        "display_name": "tl;dv",
        "website_url": "https://tldv.io",
        "products": [
            {
                "slug": "tldv",
                "display_name": "tl;dv",
                "product_type": "meeting_notetaker_saas",
                "sources": [
                    {
                        "source_key": "tldv-privacy",
                        "canonical_url": "https://tldv.io/privacy/",
                        "authority": "official_legal",
                    },
                ],
            }
        ],
    },
    {
        "slug": "github",
        "display_name": "GitHub (Microsoft)",
        "website_url": "https://github.com",
        "products": [
            {
                "slug": "github-copilot",
                "display_name": "GitHub Copilot",
                "product_type": "ai_code_assistant",
                "sources": [
                    {
                        # docs.github.com's Copilot-specific privacy statement
                        # now 301s to a third-party Trustpage JS shell - this
                        # marketing FAQ page is the best verified static
                        # source for Copilot-specific retention/training answers.
                        "source_key": "github-copilot-faq",
                        "canonical_url": "https://github.com/features/copilot",
                        "authority": "official_product_documentation",
                    },
                    {
                        "source_key": "github-general-privacy",
                        "canonical_url": "https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement",
                        "authority": "official_legal",
                    },
                ],
            }
        ],
    },
    {
        "slug": "midjourney",
        "display_name": "Midjourney",
        "website_url": "https://www.midjourney.com",
        "products": [
            {
                "slug": "midjourney",
                "display_name": "Midjourney",
                "product_type": "ai_image_generation_saas",
                "sources": [
                    {
                        # midjourney.com blocks httpx's TLS/HTTP2 fingerprint
                        # site-wide (confirmed on docs.midjourney.com and the
                        # main domain root too); disabled rather than left to
                        # fail forever.
                        "source_key": "midjourney-privacy",
                        "canonical_url": "https://docs.midjourney.com/hc/en-us/articles/32083472637453-Privacy-Policy",
                        "authority": "official_legal",
                        "enabled": False,
                    },
                ],
            }
        ],
    },
    {
        "slug": "stability-ai",
        "display_name": "Stability AI",
        "website_url": "https://stability.ai",
        "products": [
            {
                "slug": "stable-diffusion",
                "display_name": "Stable Diffusion",
                "product_type": "ai_image_generation_saas",
                "sources": [
                    {
                        "source_key": "stability-privacy-center",
                        "canonical_url": "https://stability.ai/privacy-center",
                        "authority": "official_trust_center",
                    },
                ],
            }
        ],
    },
    {
        "slug": "elevenlabs",
        "display_name": "ElevenLabs",
        "website_url": "https://elevenlabs.io",
        "products": [
            {
                "slug": "elevenlabs-api",
                "display_name": "ElevenLabs",
                "product_type": "ai_voice_generation_saas",
                "sources": [
                    {
                        "source_key": "elevenlabs-data-residency",
                        "canonical_url": "https://elevenlabs.io/docs/overview/administration/data-residency",
                        "authority": "official_product_documentation",
                    },
                ],
            }
        ],
    },
    {
        "slug": "synthesia",
        "display_name": "Synthesia",
        "website_url": "https://www.synthesia.io",
        "products": [
            {
                "slug": "synthesia",
                "display_name": "Synthesia",
                "product_type": "ai_video_generation_saas",
                "sources": [
                    {
                        "source_key": "synthesia-ai-governance",
                        "canonical_url": "https://www.synthesia.io/legal/ai-governance-practices",
                        "authority": "official_legal",
                    },
                ],
            }
        ],
    },
    {
        "slug": "heygen",
        "display_name": "HeyGen",
        "website_url": "https://www.heygen.com",
        "products": [
            {
                "slug": "heygen",
                "display_name": "HeyGen",
                "product_type": "ai_video_generation_saas",
                "sources": [
                    {
                        "source_key": "heygen-privacy",
                        "canonical_url": "https://www.heygen.com/privacy",
                        "authority": "official_legal",
                    },
                ],
            }
        ],
    },
    {
        "slug": "canva",
        "display_name": "Canva",
        "website_url": "https://www.canva.com",
        "products": [
            {
                "slug": "canva-magic-studio",
                "display_name": "Canva (Magic Studio)",
                "product_type": "ai_design_saas",
                "sources": [
                    {
                        # canva.com/trust/privacy/ blocked httpx's
                        # fingerprint specifically; the general legal privacy
                        # policy page on the same domain works fine. Keep the
                        # original source_key when swapping a URL - renaming
                        # it creates an orphaned duplicate row instead of
                        # updating in place (learned the hard way).
                        "source_key": "canva-trust-privacy",
                        "canonical_url": "https://www.canva.com/policies/privacy-policy/",
                        "authority": "official_legal",
                    },
                ],
            }
        ],
    },
    {
        "slug": "salesforce",
        "display_name": "Salesforce",
        "website_url": "https://www.salesforce.com",
        "products": [
            {
                "slug": "salesforce-einstein",
                "display_name": "Salesforce Einstein",
                "product_type": "crm_ai",
                "sources": [
                    {
                        # help.salesforce.com's article is a JS-rendered
                        # Lightning/Aura shell (no static text) - this
                        # marketing page is the verified working alternative.
                        "source_key": "salesforce-trusted-ai",
                        "canonical_url": "https://www.salesforce.com/artificial-intelligence/trusted-ai/",
                        "authority": "official_product_documentation",
                    },
                ],
            }
        ],
    },
    {
        "slug": "zoom",
        "display_name": "Zoom",
        "website_url": "https://www.zoom.com",
        "products": [
            {
                "slug": "zoom-ai-companion",
                "display_name": "Zoom AI Companion",
                "product_type": "ai_meeting_assistant",
                "sources": [
                    {
                        "source_key": "zoom-ai-whitepaper",
                        "canonical_url": "https://library.zoom.com/ai-whitepaper",
                        "authority": "official_product_documentation",
                    },
                ],
            }
        ],
    },
    {
        "slug": "slack",
        "display_name": "Slack (Salesforce)",
        "website_url": "https://slack.com",
        "products": [
            {
                "slug": "slack-ai",
                "display_name": "Slack AI",
                "product_type": "workspace_ai",
                "sources": [
                    {
                        "source_key": "slack-privacy-principles",
                        "canonical_url": "https://slack.com/trust/data-management/privacy-principles",
                        "authority": "official_trust_center",
                    },
                ],
            }
        ],
    },
    {
        "slug": "writer",
        "display_name": "Writer, Inc.",
        "website_url": "https://writer.com",
        "products": [
            {
                "slug": "writer",
                "display_name": "Writer",
                "product_type": "enterprise_ai_writing_saas",
                "sources": [
                    {
                        "source_key": "writer-trust",
                        "canonical_url": "https://writer.com/trust/",
                        "authority": "official_trust_center",
                    },
                ],
            }
        ],
    },
    {
        "slug": "copy-ai",
        "display_name": "Copy.ai",
        "website_url": "https://www.copy.ai",
        "products": [
            {
                "slug": "copy-ai",
                "display_name": "Copy.ai",
                "product_type": "ai_writing_saas",
                "sources": [
                    {
                        "source_key": "copyai-privacy-notice",
                        "canonical_url": "https://www.copy.ai/privacy-notice",
                        "authority": "official_legal",
                    },
                ],
            }
        ],
    },
    {
        "slug": "character-ai",
        "display_name": "Character Technologies",
        "website_url": "https://character.ai",
        "products": [
            {
                "slug": "character-ai",
                "display_name": "Character.AI",
                "product_type": "consumer_ai_chatbot",
                "sources": [
                    {
                        "source_key": "characterai-model-training",
                        "canonical_url": "https://character.ai/model-training",
                        "authority": "official_product_documentation",
                    },
                    {
                        # support.character.ai blocks httpx's fingerprint
                        # site-wide; the primary character.ai source above
                        # already gives real content, so this is disabled
                        # rather than dropped (kept for future retry).
                        "source_key": "characterai-privacy-policy",
                        "canonical_url": "https://support.character.ai/hc/en-us/articles/39030432883099-Privacy-Policy",
                        "authority": "official_legal",
                        "enabled": False,
                    },
                ],
            }
        ],
    },
    {
        "slug": "poe",
        "display_name": "Poe (Quora)",
        "website_url": "https://poe.com",
        "products": [
            {
                "slug": "poe",
                "display_name": "Poe",
                "product_type": "ai_model_aggregator",
                "sources": [
                    {
                        "source_key": "poe-privacy",
                        "canonical_url": "https://poe.com/pages/privacy",
                        "authority": "official_legal",
                    },
                ],
            }
        ],
    },
    {
        "slug": "you-com",
        "display_name": "You.com",
        "website_url": "https://you.com",
        "products": [
            {
                "slug": "you-com",
                "display_name": "You.com",
                "product_type": "ai_search_saas",
                "sources": [
                    {
                        # trust.you.com is a bare Vanta JS shell - unusable.
                        "source_key": "youcom-security",
                        "canonical_url": "https://home.you.com/security",
                        "authority": "official_trust_center",
                    },
                    {
                        "source_key": "youcom-privacy",
                        "canonical_url": "https://home.you.com/privacy",
                        "authority": "official_legal",
                    },
                ],
            }
        ],
    },
    {
        "slug": "replit",
        "display_name": "Replit",
        "website_url": "https://replit.com",
        "products": [
            {
                "slug": "replit-agent",
                "display_name": "Replit Agent/Ghostwriter",
                "product_type": "ai_code_assistant",
                "sources": [
                    {
                        # trust.replit.com is a bare Vanta JS shell - unusable.
                        "source_key": "replit-infosec-overview",
                        "canonical_url": "https://docs.replit.com/teams/information-security/overview",
                        "authority": "official_product_documentation",
                    },
                ],
            }
        ],
    },
    {
        "slug": "cursor",
        "display_name": "Anysphere",
        "website_url": "https://cursor.com",
        "products": [
            {
                "slug": "cursor",
                "display_name": "Cursor",
                "product_type": "ai_code_editor",
                "sources": [
                    {
                        "source_key": "cursor-data-use",
                        "canonical_url": "https://cursor.com/data-use",
                        "authority": "official_product_documentation",
                    },
                    {
                        "source_key": "cursor-security",
                        "canonical_url": "https://cursor.com/security",
                        "authority": "official_product_documentation",
                    },
                ],
            }
        ],
    },
    {
        "slug": "huggingface",
        "display_name": "Hugging Face",
        "website_url": "https://huggingface.co",
        "products": [
            {
                "slug": "huggingface-hub",
                "display_name": "Hugging Face",
                "product_type": "ml_hosting_platform",
                "sources": [
                    {
                        "source_key": "huggingface-privacy",
                        "canonical_url": "https://huggingface.co/privacy",
                        "authority": "official_legal",
                    },
                ],
            }
        ],
    },
    {
        "slug": "deepl",
        "display_name": "DeepL",
        "website_url": "https://www.deepl.com",
        "products": [
            {
                "slug": "deepl-api",
                "display_name": "DeepL",
                "product_type": "ai_translation_saas",
                "sources": [
                    {
                        # support.deepl.com blocked httpx's fingerprint
                        # specifically; the main-domain privacy policy works.
                        # Keep the original source_key when swapping a URL.
                        "source_key": "deepl-data-security",
                        "canonical_url": "https://www.deepl.com/en/privacy",
                        "authority": "official_legal",
                    },
                ],
            }
        ],
    },
    {
        "slug": "gamma",
        "display_name": "Gamma",
        "website_url": "https://gamma.app",
        "products": [
            {
                "slug": "gamma",
                "display_name": "Gamma",
                "product_type": "ai_presentations_saas",
                "sources": [
                    {
                        "source_key": "gamma-data-privacy",
                        "canonical_url": "https://help.gamma.app/en/articles/11048534-how-does-gamma-protect-my-data-and-privacy",
                        "authority": "official_support",
                    },
                ],
            }
        ],
    },
    {
        "slug": "descript",
        "display_name": "Descript",
        "website_url": "https://www.descript.com",
        "products": [
            {
                "slug": "descript",
                "display_name": "Descript",
                "product_type": "ai_audio_video_editing_saas",
                "sources": [
                    {
                        "source_key": "descript-security",
                        "canonical_url": "https://www.descript.com/security",
                        "authority": "official_trust_center",
                    },
                ],
            }
        ],
    },
    {
        "slug": "runway",
        "display_name": "Runway",
        "website_url": "https://runway.com",
        "products": [
            {
                "slug": "runway",
                "display_name": "Runway",
                "product_type": "ai_video_generation_saas",
                "sources": [
                    {
                        # Domain migrated runwayml.com -> runway.com.
                        "source_key": "runway-data-security",
                        "canonical_url": "https://runway.com/data-security",
                        "authority": "official_trust_center",
                    },
                ],
            }
        ],
    },
    {
        "slug": "microsoft-365-copilot",
        "display_name": "Microsoft 365 Copilot",
        "website_url": "https://copilot.microsoft.com",
        "products": [
            {
                # Distinct product from "microsoft-azure-openai" above -
                # different audience, packaging, and data-handling
                # commitments even though same legal parent.
                "slug": "microsoft-365-copilot",
                "display_name": "Microsoft 365 Copilot",
                "product_type": "workspace_ai",
                "sources": [
                    {
                        "source_key": "m365-copilot-privacy",
                        "canonical_url": "https://learn.microsoft.com/en-us/microsoft-365/copilot/microsoft-365-copilot-privacy",
                        "authority": "official_product_documentation",
                    },
                ],
            }
        ],
    },
    {
        "slug": "google-workspace-gemini",
        "display_name": "Google Workspace Gemini",
        "website_url": "https://workspace.google.com",
        "products": [
            {
                # Distinct product from "google-cloud-genai" above - Gemini
                # embedded in a Workspace tenant, governed by the org's own
                # Workspace agreement, not the Cloud/Developer API terms.
                "slug": "gemini-in-workspace",
                "display_name": "Gemini in Google Workspace",
                "product_type": "workspace_ai",
                "sources": [
                    {
                        "source_key": "workspace-gemini-faq",
                        "canonical_url": "https://support.google.com/a/answer/14130944?hl=en",
                        "authority": "official_support",
                    },
                ],
            }
        ],
    },
]


def upsert_seed_registry(db: Session, registry: list[dict] = SEED_REGISTRY) -> None:
    for provider_data in registry:
        provider = db.execute(
            select(Provider).where(Provider.slug == provider_data["slug"])
        ).scalar_one_or_none()
        if provider is None:
            provider = Provider(
                slug=provider_data["slug"],
                display_name=provider_data["display_name"],
                website_url=provider_data.get("website_url"),
            )
            db.add(provider)
            db.flush()
        else:
            provider.display_name = provider_data["display_name"]
            provider.website_url = provider_data.get("website_url")

        for product_data in provider_data["products"]:
            product = db.execute(
                select(Product).where(
                    Product.provider_id == provider.id,
                    Product.slug == product_data["slug"],
                )
            ).scalar_one_or_none()
            if product is None:
                product = Product(
                    provider_id=provider.id,
                    slug=product_data["slug"],
                    display_name=product_data["display_name"],
                    product_type=product_data["product_type"],
                )
                db.add(product)
                db.flush()
            else:
                product.display_name = product_data["display_name"]
                product.product_type = product_data["product_type"]

            for source_data in product_data["sources"]:
                source = db.execute(
                    select(Source).where(
                        Source.provider_id == provider.id,
                        Source.source_key == source_data["source_key"],
                    )
                ).scalar_one_or_none()
                source_class = source_data.get("source_class") or _infer_source_class(source_data["authority"])
                if source is None:
                    db.add(
                        Source(
                            provider_id=provider.id,
                            product_id=product.id,
                            source_key=source_data["source_key"],
                            canonical_url=source_data["canonical_url"],
                            authority=source_data["authority"],
                            source_class=source_class,
                            enabled=source_data.get("enabled", True),
                        )
                    )
                else:
                    source.product_id = product.id
                    source.canonical_url = source_data["canonical_url"]
                    source.authority = source_data["authority"]
                    source.source_class = source_class
                    source.enabled = source_data.get("enabled", True)

    db.commit()
