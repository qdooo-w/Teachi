export const SKILL_NAME_PATTERN = /^[\u4e00-\u9fa5a-zA-Z0-9]+(-[\u4e00-\u9fa5a-zA-Z0-9]+)*$/
export const SKILL_NAME_MAX = 64
export const SKILL_RESERVED = new Set(['anthropic', 'claude'])
export const SKILL_RESOURCE_DIRS = ['references', 'assets'] as const
export const SKILL_TEXT_EXTENSIONS = ['.md', '.txt', '.json', '.yaml', '.yml'] as const

export const SKILL_DESCRIPTION_MAX = 1024
export const SKILL_DISPLAY_NAME_MAX = 80
export const SKILL_COMPATIBILITY_MAX = 500

export const PROJECT_DESC_SKILL = 'project-description'
