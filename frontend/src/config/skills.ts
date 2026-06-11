export const SKILL_NAME_PATTERN = /^(?=.*[\p{L}\p{N}])[\p{L}\p{N}_-]+$/u
export const SKILL_NAME_MAX = 64
export const SKILL_RESERVED = new Set(['anthropic', 'claude', 'system'])
export const SKILL_RESOURCE_DIRS = ['references', 'assets', 'examples', 'templates'] as const
export const SKILL_TEXT_EXTENSIONS = ['.md', '.txt', '.json', '.yaml', '.yml'] as const

export const SKILL_DESCRIPTION_MAX = 1024
export const SKILL_DISPLAY_NAME_MAX = 80
export const SKILL_COMPATIBILITY_MAX = 500

export const PROJECT_DESC_SKILL = 'project-description'
