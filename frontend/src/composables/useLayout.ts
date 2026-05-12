// frontend/src/composables/useLayout.ts
import { computed, ref } from 'vue'

const sidebarOpen = ref(true)
const windowWidth = ref(typeof window !== 'undefined' ? window.innerWidth : 1024)
const isMobile = computed(() => windowWidth.value < 768)

function handleResize(): void {
  windowWidth.value = window.innerWidth
  sidebarOpen.value = !isMobile.value
}

function toggleSidebar(): void {
  sidebarOpen.value = !sidebarOpen.value
}

function closeSidebarOnMobile(): void {
  if (isMobile.value) sidebarOpen.value = false
}

export function useLayout() {
  return { sidebarOpen, windowWidth, isMobile, handleResize, toggleSidebar, closeSidebarOnMobile }
}
