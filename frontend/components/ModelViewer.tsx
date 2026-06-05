"use client";

// Интерактивный просмотр .glb прямо в браузере (Фаза 4, Three.js).
// Используется @react-three/fiber + drei (useGLTF, OrbitControls).

import { Canvas } from "@react-three/fiber";
import { OrbitControls, Stage, useGLTF } from "@react-three/drei";
import { Suspense, useEffect } from "react";
import { DoubleSide, Mesh } from "three";

function Model({ url }: { url: string }) {
  const { scene } = useGLTF(url);
  // Одежда — односторонняя оболочка: рендерим обе стороны, чтобы не просвечивала.
  useEffect(() => {
    scene.traverse((o) => {
      const mesh = o as Mesh;
      if (mesh.isMesh && mesh.material) {
        const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
        mats.forEach((m) => (m.side = DoubleSide));
      }
    });
  }, [scene]);
  return <primitive object={scene} />;
}

export default function ModelViewer({ url }: { url: string }) {
  return (
    <div style={{ width: "100%", height: 480, background: "#0e0e12", borderRadius: 12 }}>
      <Canvas camera={{ position: [0, 1.2, 3], fov: 45 }} shadows>
        <Suspense fallback={null}>
          <Stage environment="city" intensity={0.5} adjustCamera>
            <Model url={url} />
          </Stage>
        </Suspense>
        <OrbitControls makeDefault enablePan target={[0, 1, 0]} />
      </Canvas>
    </div>
  );
}
