# Design Spec: Chat Bubble Redesign & Logo Update

## 1. Objective
Redesign the chat bubbles in the Learnova frontend application and update the logo:
1. Cancel the AI reply's rounded dialog box design, changing its background color to blend with the main page background (`bg-[#f3f4f6]`).
2. Change the user's message dialog bubble background color to white (`bg-white`), while preserving its `rounded-3xl` corners and no-border style.
3. Replace the plain-text "Learnova" logo in the sidebar and login header with the new custom stylized SVG logo (`LEARNOVA.svg`).

## 2. Affected Files
* [ChatView.vue](file:///home/seeck/Projects/Teachi/frontend/src/views/ChatView.vue) - Vue component rendering user and AI chat bubbles.
* [App.vue](file:///home/seeck/Projects/Teachi/frontend/src/App.vue) - Main application layout containing the sidebar and auth view.
* [SKILL.md](file:///home/seeck/Projects/Teachi/.agents/skills/learnova-design/SKILL.md) - Learnova design system guidelines.

## 3. Implementation Details

### 3.1 Vue Chat Component changes
In `frontend/src/views/ChatView.vue`:
* **User Message bubble (around line 1432):**
  * Replace `bg-[#e5e7eb]` with `bg-white`.
  * Ensure the class list remains: `rounded-3xl bg-white px-4 py-2 text-[15px] leading-relaxed text-[#1f2937]`.
* **AI Message bubble (around line 1439):**
  * Replace `rounded-3xl bg-white` with `bg-[#f3f4f6]`.
  * Ensure the class list remains: `bg-[#f3f4f6] px-4 py-3 text-[15px] leading-relaxed text-[#1f2937] w-full max-w-full overflow-hidden`.
* **Control Buttons (copy, edit, delete, regenerate, version switcher):**
  * Size: Increased button size from `h-6 w-6` (24px) to `h-7 w-7` (28px).
  * SVG Icon Size: Increased SVG elements inside buttons from `h-3.5 w-3.5` (14px) to `h-4 w-4` (16px).
  * Visibility: Darkened default icon text color to `#6b7280` (gray-500) to make them stand out.
  * Interactivity: Added press feedback (`active:scale-95 transition-all duration-200`).
* **Placeholder rotation (Firefox Linux compatibility):**
  * Added `:key="currentSession?.sid || 'default'"` to the composer `<textarea>` to force DOM recreation on session switch and bypass Firefox form cache.
  * Added a watcher on `currentSession.sid` to randomize the placeholder immediately upon switching sessions.
  * Randomized the placeholder upon successful message sending.

### 3.2 Design Guidelines updates
In `.agents/skills/learnova-design/SKILL.md`:
* Update main UI backgrounds list to reflect `bg-white (用户聊天气泡)`.
* Update chat bubble descriptions under section 4.1 to reflect the new bubble layouts.

### 3.3 Markdown Elements (Tables & Mermaid) Styling updates
In `frontend/src/style.css`:
* **Tables:**
  * Background: transparent (seamlessly blends with the page background `#f3f4f6`).
  * Borders (`th`, `td`): change from `1px solid #e5e7eb` to a darker `1px solid #cbd5e1` to stand out better on the gray background.
  * Header (`th`): background color changed to `#e2e8f0` (slate-200) for distinct header formatting.
  * Even rows: background color changed to `#ffffff` (white) for stripe contrast.
  * Hover rows: `tr:hover td` background color changed to `#e2e8f0` (slate-200).
* **Mermaid blocks:**
  * Background: transparent (no white card background).
  * Border: none (fully flat seamless layout).
  * Padding: update to `0.5em 0` to preserve vertical spacing.
  * Hover styles: remove the white hover background and box shadows, keep transition properties.

### 3.4 Logo Update
In `frontend/src/App.vue`:
* **Sidebar logo header (around line 627):**
  * Replace the `<span ...>Learnova</span>` component with the stylized inline SVG from `LEARNOVA.svg`, styled as `h-4 w-auto text-[#1f2937] transition-colors duration-200` to fit the sidebar perfectly.
* **Auth (Login/Register) header (around line 487):**
  * Replace the `<div ...>Learnova</div>` text logo with the stylized inline SVG from `LEARNOVA.svg`, styled as `h-6 w-auto text-[#1f2937]`.

## 4. Verification Plan
* Compile/Build the frontend code to ensure no syntax/template issues.
* Inspect the styles locally if possible (we can verify static types and build).
