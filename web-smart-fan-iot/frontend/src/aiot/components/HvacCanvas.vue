<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import type { FrameReadyV2 } from '../../lib/contracts-v2.generated';
import type { DeviceDescriptor } from '../../lib/ws-server.generated';
import { HvacScene, type SceneStats } from '../scene/renderer';
import type { Ranges } from '../scene/model';
const props = defineProps<{
  device: DeviceDescriptor;
  frame?: FrameReadyV2;
  ranges?: Ranges;
  selected: string;
}>();
const emit = defineEmits<{
  select: [id: string];
  stats: [value: SceneStats];
}>();
const canvas = ref<HTMLCanvasElement>();
const failure = ref('');
let scene: HvacScene | undefined;
let media: MediaQueryList | undefined;
const reduced = () => {
  if (scene) scene.reducedMotion = media?.matches ?? false;
};
onMounted(() => {
  try {
    scene = new HvacScene(
      canvas.value!,
      props.device,
      (id) => emit('select', id),
      (value) => emit('stats', value),
    );
    scene.update(props.frame, props.ranges, props.device);
    scene.focus(props.selected);
    media = matchMedia('(prefers-reduced-motion: reduce)');
    reduced();
    media.addEventListener('change', reduced);
  } catch {
    failure.value =
      'Visualização 3D indisponível neste navegador. Os componentes e leituras continuam disponíveis na lista textual.';
  }
});
watch(
  () => [props.frame, props.ranges, props.device] as const,
  () => scene?.update(props.frame, props.ranges, props.device),
);
watch(
  () => props.selected,
  (id) => scene?.focus(id),
);
onBeforeUnmount(() => {
  media?.removeEventListener('change', reduced);
  scene?.dispose();
});
</script>
<template>
  <p v-if="failure" class="notice" role="status">{{ failure }}</p>
  <div class="canvas-shell">
    <canvas
      ref="canvas"
      tabindex="0"
      aria-label="Cena 3D do ar-condicionado; arraste para girar, use a lista textual para selecionar componentes"
      @webglcontextlost="
        failure = 'Contexto 3D perdido. Use a lista textual ou reabra a página.'
      "
    /><button
      class="button secondary camera-reset"
      @click="scene?.resetCamera()"
    >
      Recentrar câmera
    </button>
  </div>
</template>
<style scoped>
.canvas-shell {
  height: 440px;
  position: relative;
  border-radius: 16px;
  overflow: hidden;
  background: #eaf1f2;
}
canvas {
  display: block;
  width: 100%;
  height: 100%;
  touch-action: none;
}
.camera-reset {
  position: absolute;
  right: 1rem;
  bottom: 1rem;
}
@media (max-width: 600px) {
  .canvas-shell {
    height: 320px;
  }
}
</style>
