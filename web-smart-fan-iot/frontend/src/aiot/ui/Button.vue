<script setup lang="ts">
import { Primitive, type PrimitiveProps } from 'reka-ui';
import { cva } from 'class-variance-authority';
interface Props extends PrimitiveProps {
  variant?: 'primary' | 'outline' | 'ghost';
}
withDefaults(defineProps<Props>(), { as: 'button', variant: 'outline' });
const variants = cva(
  'pv-button ui:inline-flex ui:items-center ui:justify-center ui:gap-2 ui:rounded-lg ui:border ui:border-solid ui:px-3 ui:py-2 ui:text-sm ui:font-semibold ui:transition-colors ui:disabled:cursor-not-allowed ui:disabled:bg-slate-100 ui:disabled:text-slate-600 ui:disabled:border-slate-400 ui:focus-visible:outline-2 ui:focus-visible:outline-offset-2 ui:focus-visible:outline-teal-700',
  {
    variants: {
      variant: {
        primary:
          'ui:border-teal-700 ui:bg-teal-700 ui:text-white ui:hover:bg-teal-800',
        outline:
          'ui:border-slate-500 ui:bg-white ui:text-slate-800 ui:hover:bg-slate-50',
        ghost:
          'ui:border-transparent ui:bg-transparent ui:text-slate-700 ui:hover:bg-slate-100',
      },
    },
  },
);
</script>
<template>
  <Primitive :as="as" :as-child="asChild" :class="variants({ variant })"
    ><slot
  /></Primitive>
</template>
<style scoped>
.pv-button {
  font-size: 1rem;
  min-height: 3.14286rem;
  text-decoration: none;
  line-height: 1.4;
}
.pv-button:disabled {
  cursor: not-allowed;
}
</style>
