// Zustand store tracking the currently active document across components.
import { create } from 'zustand'

export const useAppStore = create((set) => ({
  activeDocId: null,
  setActiveDocId: (id) => set({ activeDocId: id }),
}))