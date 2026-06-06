// frontend/src/composables/useNotification.ts
import { ref, computed } from 'vue'

export type NotificationType = 'success' | 'error'

export interface NotificationItem {
  id: string
  type: NotificationType
  message: string
  details?: string
  expanded?: boolean
}

// 维护一个全局的通知列表
const notifications = ref<NotificationItem[]>([])

export function showNotification(
  type: NotificationType,
  message: string,
  details?: string,
  duration = 5000 // 默认自动关闭时间设为 5 秒
) {
  const id = Math.random().toString(36).substring(2, 9)
  const newItem: NotificationItem = {
    id,
    type,
    message,
    details,
    expanded: false,
  }

  notifications.value.push(newItem)

  // 默认 5 秒后自动移除该提示
  if (duration > 0) {
    setTimeout(() => {
      removeNotification(id)
    }, duration)
  }
}

export function showSuccess(message: string, details?: string, duration = 5000) {
  showNotification('success', message, details, duration)
}

export function showError(message: string, details?: string, duration = 5000) {
  showNotification('error', message, details, duration)
}

export function removeNotification(id: string) {
  notifications.value = notifications.value.filter((n) => n.id !== id)
}

export function clearAllNotifications() {
  notifications.value = []
}

export function toggleNotificationExpanded(id: string) {
  const item = notifications.value.find((n) => n.id === id)
  if (item) {
    item.expanded = !item.expanded
  }
}

// 提供一个向下兼容的单通知状态 (由堆栈派生)
const state = computed(() => {
  if (notifications.value.length === 0) {
    return {
      show: false,
      type: 'error' as NotificationType,
      message: '',
      details: '',
    }
  }
  const last = notifications.value[notifications.value.length - 1]
  return {
    show: true,
    type: last.type,
    message: last.message,
    details: last.details,
  }
})

export function useNotification() {
  return {
    state,
    notifications,
    showSuccess,
    showError,
    removeNotification,
    clearAllNotifications,
    toggleNotificationExpanded,
    hideNotification: clearAllNotifications, // 兼容原 hideNotification 调用
  }
}
