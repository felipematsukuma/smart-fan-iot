/** Small shadcn-vue compositions, adapted to the isolated ui: utility prefix. */
import { defineComponent, h, type PropType } from 'vue';

export const Card = defineComponent({
  inheritAttrs: false,
  setup(_, { attrs, slots }) {
    return () =>
      h(
        'section',
        {
          ...attrs,
          class: [
            'pv-card ui:rounded-xl ui:border ui:border-solid ui:border-slate-200 ui:bg-white ui:shadow-xs',
            attrs.class,
          ],
        },
        slots.default?.(),
      );
  },
});
export type Tone = 'neutral' | 'good' | 'warning' | 'danger';
const tones = {
  neutral: 'ui:bg-slate-100 ui:text-slate-700',
  good: 'ui:bg-teal-50 ui:text-teal-800',
  warning: 'ui:bg-amber-50 ui:text-amber-900',
  danger: 'ui:bg-red-50 ui:text-red-800',
};
export const Badge = defineComponent({
  inheritAttrs: false,
  props: { tone: { type: String as PropType<Tone>, default: 'neutral' } },
  setup(props, { attrs, slots }) {
    return () =>
      h(
        'span',
        {
          ...attrs,
          class: [
            'pv-badge ui:inline-flex ui:items-center ui:gap-1.5 ui:rounded-md ui:px-2.5 ui:py-1 ui:text-sm ui:font-semibold',
            tones[props.tone],
            attrs.class,
          ],
        },
        slots.default?.(),
      );
  },
});
export const Alert = defineComponent({
  inheritAttrs: false,
  props: { tone: { type: String as PropType<Tone>, default: 'neutral' } },
  setup(props, { attrs, slots }) {
    return () =>
      h(
        'div',
        {
          role: 'status',
          ...attrs,
          class: [
            'pv-alert ui:rounded-lg ui:border ui:border-solid ui:border-current ui:p-4 ui:text-sm',
            tones[props.tone],
            attrs.class,
          ],
        },
        slots.default?.(),
      );
  },
});
export const Skeleton = defineComponent({
  setup(_, { attrs }) {
    return () =>
      h('div', {
        ...attrs,
        'aria-hidden': true,
        class: [
          'pv-skeleton ui:h-8 ui:rounded-md ui:bg-slate-100',
          attrs.class,
        ],
      });
  },
});
