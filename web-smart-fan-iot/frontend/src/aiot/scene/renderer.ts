import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import type { FrameReadyV2 } from '../../lib/contracts-v2.generated';
import type { DeviceDescriptor } from '../../lib/ws-server.generated';
import { state, type Ranges, type SensorField } from './model';

export interface SceneStats {
  fps: number;
  calls: number;
  triangles: number;
  geometries: number;
  frozen: boolean;
  fanAngle: number;
}
const markerPositions: Record<SensorField, [number, number, number]> = {
  current_a: [0.65, 1.2, -0.75],
  compressor_case_temp_c: [1.25, 1.4, 0.45],
  vibration_rms_mm_s: [0.9, 0.45, 0.85],
  indoor_temp_c: [-2.8, 1.1, 0.6],
  outdoor_temp_c: [3.4, 1.1, 0.4],
};

/** Geometry is built once per selected device. Frames replace a buffer only. */
export class HvacScene {
  private canvas: HTMLCanvasElement;
  private device: DeviceDescriptor;
  private select: (id: string) => void;
  private stats: (value: SceneStats) => void;
  private scene = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(42, 1, 0.1, 50);
  private renderer: THREE.WebGLRenderer;
  private controls: OrbitControls;
  private resources = new Set<THREE.BufferGeometry | THREE.Material>();
  private meshes = new Map<string, THREE.Mesh>();
  private fan = new THREE.Group();
  private compressor = new THREE.Group();
  private indoor: THREE.ShaderMaterial;
  private outdoor: THREE.ShaderMaterial;
  private buffer: {
    frame: FrameReadyV2 | undefined;
    ranges: Ranges | undefined;
  } = { frame: undefined, ranges: undefined };
  private observer: ResizeObserver;
  private ray = new THREE.Raycaster();
  private handle = 0;
  private disposed = false;
  private previous = 0;
  private nextRender = 0;
  private phase = 0;
  private statsStart = 0;
  private renders = 0;
  reducedMotion = false;

  constructor(
    canvas: HTMLCanvasElement,
    device: DeviceDescriptor,
    select: (id: string) => void,
    stats: (value: SceneStats) => void,
  ) {
    this.canvas = canvas;
    this.device = device;
    this.select = select;
    this.stats = stats;
    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: false,
      powerPreference: 'low-power',
    });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
    this.renderer.setClearColor('#eaf1f2');
    this.camera.position.set(7, 6, 8);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.target.set(0, 0.9, 0);
    this.controls.enableDamping = false;
    this.controls.minDistance = 5;
    this.controls.maxDistance = 18;
    this.controls.maxPolarAngle = Math.PI * 0.48;
    this.controls.enablePan = false;
    this.controls.update();
    this.scene.add(new THREE.HemisphereLight('#ffffff', '#829693', 2.4));
    const light = new THREE.DirectionalLight('#ffffff', 2.3);
    light.position.set(3, 7, 5);
    this.scene.add(light);
    this.indoor = this.heatMaterial();
    this.outdoor = this.heatMaterial();
    this.build();
    this.observer = new ResizeObserver(() => this.resize());
    this.observer.observe(canvas.parentElement!);
    this.resize();
    canvas.addEventListener('pointerup', this.pick);
    canvas.addEventListener('webglcontextlost', this.contextLost);
    this.handle = requestAnimationFrame(this.draw);
  }
  private material(color: string) {
    const material = new THREE.MeshStandardMaterial({
      color,
      roughness: 0.7,
      metalness: 0.12,
    });
    this.resources.add(material);
    return material;
  }
  private geometry<T extends THREE.BufferGeometry>(geometry: T): T {
    this.resources.add(geometry);
    return geometry;
  }
  private box(
    size: [number, number, number],
    position: [number, number, number],
    color: string,
    parent: THREE.Object3D = this.scene,
  ) {
    const mesh = new THREE.Mesh(
      this.geometry(new THREE.BoxGeometry(...size)),
      this.material(color),
    );
    mesh.position.set(...position);
    parent.add(mesh);
    return mesh;
  }
  private heatMaterial() {
    const material = new THREE.ShaderMaterial({
      uniforms: { temperature: { value: 0 }, available: { value: 0 } },
      vertexShader:
        'varying vec2 vUv; void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}',
      fragmentShader:
        'uniform float temperature; uniform float available; varying vec2 vUv; void main(){float t=clamp((temperature-18.)/24.,0.,1.); vec3 c=mix(vec3(.24,.65,.76),vec3(.94,.59,.31),t); float radial=1.-smoothstep(0.,.8,length(vUv-vec2(.5))); c=mix(vec3(.86,.91,.91),c,.25+.45*radial); gl_FragColor=vec4(mix(vec3(.82,.86,.87),c,available),1.);}',
      side: THREE.DoubleSide,
    });
    this.resources.add(material);
    return material;
  }
  private floor(x: number, material: THREE.ShaderMaterial) {
    const mesh = new THREE.Mesh(
      this.geometry(new THREE.PlaneGeometry(3.7, 4)),
      material,
    );
    mesh.rotation.x = -Math.PI / 2;
    mesh.position.set(x, 0.015, 0);
    this.scene.add(mesh);
  }
  private marker(id: string, position: [number, number, number], radius = 0.1) {
    const mesh = new THREE.Mesh(
      this.geometry(new THREE.SphereGeometry(radius, 10, 8)),
      this.material('#8b9aab'),
    );
    mesh.position.set(...position);
    mesh.userData.id = id;
    this.scene.add(mesh);
    this.meshes.set(id, mesh);
    return mesh;
  }
  private build() {
    this.box([7.9, 0.12, 4.3], [0.2, -0.07, 0], '#d9e4e5');
    this.floor(-1.9, this.indoor);
    this.floor(2, this.outdoor);
    this.box([3.8, 2.65, 0.12], [-1.95, 1.32, -2], '#fafcfb');
    this.box([0.12, 2.65, 3.9], [-3.9, 1.32, -0.05], '#d2e1e1');
    this.box([0.12, 2.65, 2.7], [0, 1.32, -1], '#f2f5f2');
    this.box([1.45, 0.7, 0.05], [-2.2, 1.65, -1.91], '#92bdc6');
    this.box([2.1, 0.45, 0.42], [-1.4, 2.15, -1.67], '#fffdf7');
    for (let index = 0; index < 5; index++)
      this.box(
        [1.85, 0.025, 0.03],
        [-1.4, 2.03 + index * 0.04, -1.445],
        '#a6baba',
      );
    this.box([1.5, 0.38, 0.65], [-2.5, 0.25, 0.75], '#799b98');
    this.box([1.5, 0.6, 0.15], [-2.5, 0.6, 0.45], '#8caaa6');
    this.box([0.75, 0.08, 0.55], [-1, 0.35, 1.1], '#d2b187');
    // Exposed condenser and compressor make the monitored parts selectable.
    this.box([2.7, 0.14, 1.3], [2, 0.18, -0.15], '#f6faf9');
    this.box([2.7, 1.5, 0.12], [2, 0.93, -0.83], '#c8d7d9');
    for (let index = 0; index < 9; index++)
      this.box(
        [0.04, 1.2, 0.08],
        [0.85 + index * 0.27, 0.95, -0.73],
        '#829d9f',
      );
    this.compressor.position.set(1.25, 0.7, -0.1);
    const body = new THREE.Mesh(
      this.geometry(new THREE.CylinderGeometry(0.3, 0.34, 0.85, 20)),
      this.material('#8b9aab'),
    );
    body.userData.id = this.device.id;
    this.meshes.set(this.device.id, body);
    this.compressor.add(body);
    this.scene.add(this.compressor);
    const cap = new THREE.Mesh(
      this.geometry(new THREE.SphereGeometry(0.3, 12, 8)),
      this.material('#516775'),
    );
    cap.scale.y = 0.4;
    cap.position.y = 0.42;
    this.compressor.add(cap);
    this.fan.position.set(2.65, 0.95, -0.03);
    const hub = new THREE.Mesh(
      this.geometry(new THREE.CylinderGeometry(0.15, 0.15, 0.2, 16)),
      this.material('#476b73'),
    );
    hub.rotation.x = Math.PI / 2;
    this.fan.add(hub);
    for (let index = 0; index < 4; index++) {
      const blade = this.box(
        [0.24, 0.65, 0.06],
        [0, 0.28, 0],
        '#658d96',
        new THREE.Group(),
      );
      const arm = blade.parent!;
      arm.rotation.z = (index * Math.PI) / 2;
      arm.userData.id = this.device.actuator_ids.condenser_fan_on;
      this.fan.add(arm);
    }
    this.scene.add(this.fan);
    const ring = new THREE.Mesh(
      this.geometry(new THREE.TorusGeometry(0.7, 0.035, 6, 32)),
      this.material('#718d94'),
    );
    ring.position.copy(this.fan.position);
    ring.position.z = 0.15;
    this.scene.add(ring);
    this.box([0.1, 1.1, 0.1], [0.15, 1.35, -0.5], '#c8a76a');
    this.box([1.1, 0.1, 0.1], [0.7, 0.8, -0.5], '#c8a76a');
    for (const [field, id] of Object.entries(this.device.sensor_ids))
      this.marker(id, markerPositions[field as SensorField]);
    this.marker(
      this.device.actuator_ids.compressor_on,
      [1.25, 1.65, -0.05],
      0.13,
    );
    this.marker(
      this.device.actuator_ids.condenser_fan_on,
      [2.65, 1.85, -0.05],
      0.13,
    );
  }
  update(
    frame: FrameReadyV2 | undefined,
    ranges?: Ranges,
    device = this.device,
  ) {
    this.device = device;
    this.buffer = { frame, ranges };
  }
  focus(id: string) {
    for (const [key, mesh] of this.meshes) {
      const material = mesh.material as THREE.MeshStandardMaterial;
      material.emissive.set(key === id ? '#415a65' : '#000000');
      mesh.scale.setScalar(key === id ? 1.2 : 1);
    }
  }
  resetCamera() {
    this.camera.position.set(7, 6, 8);
    this.controls.target.set(0, 0.9, 0);
    this.controls.update();
  }
  private resize() {
    const rect = this.canvas.parentElement!.getBoundingClientRect();
    const width = Math.max(1, rect.width),
      height = Math.max(1, rect.height);
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
  }
  private pick = (event: PointerEvent) => {
    const rect = this.canvas.getBoundingClientRect();
    this.ray.setFromCamera(
      new THREE.Vector2(
        ((event.clientX - rect.left) / rect.width) * 2 - 1,
        (-(event.clientY - rect.top) / rect.height) * 2 + 1,
      ),
      this.camera,
    );
    for (const hit of this.ray.intersectObjects(this.scene.children, true)) {
      let object: THREE.Object3D | null = hit.object;
      while (object) {
        if (object.userData.id) {
          this.select(String(object.userData.id));
          return;
        }
        object = object.parent;
      }
    }
  };
  private contextLost = (event: Event) => {
    event.preventDefault();
    this.dispose();
  };
  private draw = (time: number) => {
    if (this.disposed) return;
    this.handle = requestAnimationFrame(this.draw);
    if (time < this.nextRender) return;
    const period = 1000 / 30;
    this.nextRender = time + period - ((time - this.nextRender) % period);
    if (!this.statsStart) this.statsStart = time;
    const delta = this.previous
      ? Math.min(0.1, (time - this.previous) / 1000)
      : 0;
    this.previous = time;
    const data = state(
      this.buffer.frame,
      this.device,
      Date.now(),
      this.buffer.ranges,
    );
    if (data) {
      if (!this.reducedMotion) {
        if (data.fan) this.fan.rotation.z += delta * 4;
        this.phase += delta;
        this.compressor.position.x =
          1.25 +
          (data.compressor && data.vibration != null
            ? Math.sin(this.phase * 35) * Math.min(data.vibration, 12) * 0.003
            : 0);
      }
      (
        this.meshes.get(this.device.id)!.material as THREE.MeshStandardMaterial
      ).color.set(data.equipmentColor);
      for (const [id, color] of Object.entries(data.sensorColors))
        (this.meshes.get(id)!.material as THREE.MeshStandardMaterial).color.set(
          color,
        );
      for (const [field, on] of Object.entries({
        compressor_on: data.compressor,
        condenser_fan_on: data.fan,
      }))
        (
          this.meshes.get(
            this.device.actuator_ids[
              field as keyof DeviceDescriptor['actuator_ids']
            ],
          )!.material as THREE.MeshStandardMaterial
        ).color.set(on ? '#377fa4' : '#8b9aab');
      for (const [material, temperature] of [
        [this.indoor, data.indoor],
        [this.outdoor, data.outdoor],
      ] as const) {
        material.uniforms.available!.value = temperature == null ? 0 : 1;
        if (temperature != null)
          material.uniforms.temperature!.value = temperature;
      }
    }
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
    this.renders++;
    if (time - this.statsStart >= 1000) {
      const info = this.renderer.info;
      this.stats({
        fps: (this.renders * 1000) / (time - this.statsStart),
        calls: info.render.calls,
        triangles: info.render.triangles,
        geometries: info.memory.geometries,
        frozen: data == null || this.reducedMotion,
        fanAngle: this.fan.rotation.z,
      });
      this.statsStart = time;
      this.renders = 0;
    }
  };
  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    cancelAnimationFrame(this.handle);
    this.observer.disconnect();
    this.canvas.removeEventListener('pointerup', this.pick);
    this.canvas.removeEventListener('webglcontextlost', this.contextLost);
    this.controls.dispose();
    this.resources.forEach((resource) => resource.dispose());
    this.renderer.dispose();
    this.scene.clear();
    this.meshes.clear();
  }
}
