import { ref } from 'vue'

const searchQuery = ref('')
const triggerSearch = ref(0)
const showUploadModal = ref(false)

export function useCommunity() {
  return {
    searchQuery,
    triggerSearch,
    showUploadModal,
  }
}
