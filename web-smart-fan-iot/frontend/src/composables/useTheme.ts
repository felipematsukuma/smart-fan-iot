import { onMounted, ref } from 'vue';

const STORAGE_KEY = 'ventora-theme';

export function useTheme() {
  const isDark = ref(true);

  const applyTheme = (dark: boolean) => {
    isDark.value = dark;
    document.documentElement.classList.toggle('dark', dark);
    localStorage.setItem(STORAGE_KEY, dark ? 'dark' : 'light');
  };

  onMounted(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    applyTheme(stored !== 'light');
  });

  const toggleTheme = () => applyTheme(!isDark.value);

  return { isDark, toggleTheme };
}
