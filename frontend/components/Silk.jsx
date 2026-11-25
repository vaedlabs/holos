'use client'

// The moving silk behind the home page and the sign-in pages (owner, 23 and 25 Nov 2026). One full-screen
// shader plane drawn with three.js directly: no React renderer for three (and so no THREE.Clock,
// which @react-three/fiber 9 still creates and three deprecates). R7.
import { useEffect, useRef, useSyncExternalStore } from 'react'
import { Color, Mesh, OrthographicCamera, PlaneGeometry, Scene, ShaderMaterial, WebGLRenderer } from 'three'

import { useMediaQuery } from '@/hooks/useMediaQuery'

const hexToNormalizedRGB = (hex) => {
  const h = hex.replace('#', '')
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255)
}

// The plane already spans the screen (-1 to 1), so no camera transform is needed
const vertexShader = `
varying vec2 vUv;

void main() {
  vUv = uv;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`

const fragmentShader = `
varying vec2 vUv;

uniform float uTime;
uniform vec3  uColor;
uniform float uSpeed;
uniform float uScale;
uniform float uRotation;
uniform float uNoiseIntensity;

const float e = 2.71828182845904523536;

float noise(vec2 texCoord) {
  float G = e;
  vec2  r = (G * sin(G * texCoord));
  return fract(r.x * r.y * (1.0 + texCoord.x));
}

vec2 rotateUvs(vec2 uv, float angle) {
  float c = cos(angle);
  float s = sin(angle);
  mat2  rot = mat2(c, -s, s, c);
  return rot * uv;
}

void main() {
  float rnd        = noise(gl_FragCoord.xy);
  vec2  uv         = rotateUvs(vUv * uScale, uRotation);
  vec2  tex        = uv * uScale;
  float tOffset    = uSpeed * uTime;

  tex.y += 0.03 * sin(8.0 * tex.x - tOffset);

  float pattern = 0.6 +
                  0.4 * sin(5.0 * (tex.x + tex.y +
                                   cos(3.0 * tex.x + 5.0 * tex.y) +
                                   0.02 * tOffset) +
                           sin(20.0 * (tex.x + tex.y - 0.1 * tOffset)));

  vec4 col = vec4(uColor, 1.0) * vec4(pattern) - rnd / 15.0 * uNoiseIntensity;
  col.a = 1.0;
  gl_FragColor = col;
}
`

// The theme's --silk colour for the current mode (app/theme.css): the shader needs a hex, not a
// role, so it's read from the page, and read again when the device switches light and dark
function themeSilk() {
  return getComputedStyle(document.documentElement).getPropertyValue('--silk').trim()
}
function onSchemeChange(onChange) {
  const scheme = window.matchMedia('(prefers-color-scheme: dark)')
  scheme.addEventListener('change', onChange)
  return () => scheme.removeEventListener('change', onChange)
}

export default function Silk({ speed = 5, scale = 1, noiseIntensity = 1.5, rotation = 0 }) {
  const box = useRef(null)
  const material = useRef(null)
  const draw = useRef(null)
  const color = useSyncExternalStore(onSchemeChange, themeSilk, () => '')
  const still = useMediaQuery('(prefers-reduced-motion: reduce)')
  const hex = /^#[0-9a-f]{6}$/i.test(color)

  // The scene: built once the box is there, sized with it, freed when it goes
  useEffect(() => {
    const el = box.current
    if (!el) return undefined
    const renderer = new WebGLRenderer({ antialias: false })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    el.appendChild(renderer.domElement)
    const geometry = new PlaneGeometry(2, 2)
    const mat = new ShaderMaterial({
      vertexShader,
      fragmentShader,
      uniforms: {
        uTime: { value: 0 }, uColor: { value: new Color() }, uSpeed: { value: 0 }, uScale: { value: 1 },
        uRotation: { value: 0 }, uNoiseIntensity: { value: 0 },
      },
    })
    const scene = new Scene()
    scene.add(new Mesh(geometry, mat))
    const camera = new OrthographicCamera(-1, 1, 1, -1, 0, 1)
    material.current = mat
    draw.current = () => renderer.render(scene, camera)
    const resize = () => {
      renderer.setSize(el.clientWidth, el.clientHeight, false)
      draw.current()
    }
    const observer = new ResizeObserver(resize)
    observer.observe(el)
    return () => {
      observer.disconnect()
      material.current = null
      draw.current = null
      geometry.dispose()
      mat.dispose()
      renderer.dispose()
      renderer.domElement.remove()
    }
  }, [hex])

  // The look follows the props and the theme colour (set as the old renderer did: linear RGB)
  useEffect(() => {
    const m = material.current
    if (!m || !hex) return
    m.uniforms.uSpeed.value = speed
    m.uniforms.uScale.value = scale
    m.uniforms.uNoiseIntensity.value = noiseIntensity
    m.uniforms.uRotation.value = rotation
    m.uniforms.uColor.value.setRGB(...hexToNormalizedRGB(color))
    draw.current?.()
  }, [speed, scale, noiseIntensity, rotation, color, hex])

  // It moves on each frame, unless the person prefers reduced motion: then it holds still
  useEffect(() => {
    if (still || !hex) return undefined
    let frame
    let last = performance.now()
    const tick = (now) => {
      const m = material.current
      if (m) m.uniforms.uTime.value += 0.1 * ((now - last) / 1000)
      last = now
      draw.current?.()
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [still, hex])

  if (!hex) return null // the theme's colour didn't read as a hex: no silk rather than a wrong one
  return <div ref={box} aria-hidden="true" className="absolute inset-0 -z-10 [&>canvas]:block [&>canvas]:size-full" />
}
