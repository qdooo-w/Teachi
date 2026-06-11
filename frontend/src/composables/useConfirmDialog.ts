import { readonly, ref } from 'vue'

export type ConfirmTone = 'default' | 'warning' | 'danger'

export interface ConfirmDialogOptions {
  title: string
  message: string
  confirmText?: string
  cancelText?: string
  tone?: ConfirmTone
}

export interface ConfirmDialogState {
  open: boolean
  title: string
  message: string
  confirmText: string
  cancelText: string
  tone: ConfirmTone
}

const state = ref<ConfirmDialogState>({
  open: false,
  title: '',
  message: '',
  confirmText: '确认',
  cancelText: '取消',
  tone: 'default',
})

let resolver: ((confirmed: boolean) => void) | null = null

function settle(confirmed: boolean): void {
  const resolve = resolver
  resolver = null
  state.value = {
    ...state.value,
    open: false,
  }
  resolve?.(confirmed)
}

export function confirmDialog(options: ConfirmDialogOptions): Promise<boolean> {
  if (resolver) settle(false)

  state.value = {
    open: true,
    title: options.title,
    message: options.message,
    confirmText: options.confirmText ?? '确认',
    cancelText: options.cancelText ?? '取消',
    tone: options.tone ?? 'default',
  }

  return new Promise<boolean>((resolve) => {
    resolver = resolve
  })
}

export function confirmWarning(options: Omit<ConfirmDialogOptions, 'tone'>): Promise<boolean> {
  return confirmDialog({ ...options, tone: 'warning' })
}

export function confirmDanger(options: Omit<ConfirmDialogOptions, 'tone'>): Promise<boolean> {
  return confirmDialog({ ...options, tone: 'danger' })
}

export function useConfirmDialog() {
  return {
    confirmState: readonly(state),
    confirmDialog,
    confirmWarning,
    confirmDanger,
    resolveConfirm: () => settle(true),
    cancelConfirm: () => settle(false),
  }
}
