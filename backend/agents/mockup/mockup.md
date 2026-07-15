---
model: gemini-2.5-flash-image-preview
max_tokens: 0
---

# Mockup Instruction Template

This file is not a system prompt — it is the **instruction template** sent
to Gemini's image editor along with the original photo. The Orchestrator
fills in the `{{ … }}` placeholders from the final 9 tips before dispatch.

---

Edit the attached retail display photograph to reflect the following
merchandising improvements. Preserve the **exact same store, fixtures,
lighting angle, and camera framing** — only rearrange or restyle the
products, signage, and props as described.

**Brand voice to maintain in any signage:** {{ brand_voice }}

**Changes to make (in priority order):**
{{ prioritised_actions }}

**Do NOT:**
- Add products that were not in the original scene.
- Change the store architecture, floor, ceiling, or wall colour.
- Add text that isn't specified above.
- Introduce people or hands.

Return a single edited image, same aspect ratio as the input.
