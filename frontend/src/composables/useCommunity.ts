import { ref } from 'vue'

const searchQuery = ref('')
const triggerSearch = ref(0)

export function useCommunity() {
  return {
    searchQuery,
    triggerSearch,
  }
}
