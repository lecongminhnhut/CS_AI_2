import * as THREE from "./vendor/three.module.min.js";

const fill = { hidden: 0x382026, innocent: 0x34372b, criminal: 0x541f28 };

export function mountBoard(layer, board) {
  const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(0, 1, 0, -1, 1, 120);
  camera.position.z = 80;
  const outline = new THREE.Shape();
  const edge = .5;
  const corner = .415;
  outline.moveTo(-corner, -edge);
  outline.lineTo(corner, -edge);
  outline.quadraticCurveTo(edge, -edge, edge, -corner);
  outline.lineTo(edge, corner);
  outline.quadraticCurveTo(edge, edge, corner, edge);
  outline.lineTo(-corner, edge);
  outline.quadraticCurveTo(-edge, edge, -edge, corner);
  outline.lineTo(-edge, -corner);
  outline.quadraticCurveTo(-edge, -edge, -corner, -edge);
  const geometry = new THREE.ExtrudeGeometry(outline, { depth: 1, bevelEnabled: false });
  geometry.translate(0, 0, -.5);
  const edgeMaterial = new THREE.MeshBasicMaterial({ color: 0x170d15 });
  const stage = layer.parentElement;
  let width = 0;
  let height = 0;
  let frame;
  let active = true;
  let cards = [];
  layer.append(renderer.domElement);
  stage.classList.add("has-3d");

  function draw() {
    renderer.render(scene, camera);
    frame = undefined;
  }

  function fit() {
    if (!active) return;
    const bounds = layer.getBoundingClientRect();
    if (width !== bounds.width || height !== bounds.height) {
      width = bounds.width;
      height = bounds.height;
      renderer.setPixelRatio(Math.min(devicePixelRatio, width < 600 ? 1 : 1.75));
      renderer.setSize(width, height);
      camera.right = width;
      camera.bottom = -height;
      camera.updateProjectionMatrix();
    }
    for (const { element, mesh } of cards) {
      // Keep the shadow at the grid position while the HTML card moves above it.
      const { offsetLeft: left, offsetTop: top, offsetWidth: w, offsetHeight: h } = element;
      mesh.position.set(left + w / 2, -(top + h / 2) - 3, 0);
      mesh.scale.set(Math.max(w - 7, 1), Math.max(h - 2, 1), 6);
    }
    if (frame === undefined) frame = requestAnimationFrame(draw);
  }

  const observer = new ResizeObserver(fit);
  observer.observe(layer);
  renderer.domElement.addEventListener("webglcontextlost", () => {
    active = false;
    cancelAnimationFrame(frame);
    observer.disconnect();
    stage.classList.remove("has-3d");
    renderer.domElement.remove();
  }, { once: true });

  function sync() {
    if (!active) return;
    const previous = new Map(cards.map(card => [card.element, card]));
    cards = [...board.querySelectorAll(".card")].map(element => {
      const color = fill[element.dataset.status];
      let card = previous.get(element);
      if (card) {
        previous.delete(element);
        card.face.color.setHex(color);
      } else {
        const face = new THREE.MeshBasicMaterial({ color });
        const mesh = new THREE.Mesh(geometry, [face, edgeMaterial]);
        scene.add(mesh);
        card = { element, face, mesh };
      }
      card.mesh.visible = !element.classList.contains("flipping");
      return card;
    });
    for (const card of previous.values()) {
      scene.remove(card.mesh);
      card.face.dispose();
    }
    fit();
  }
  return sync;
}
