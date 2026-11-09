/**
 * Blandina-inspired Kinetic Interactive Canvas Animation
 * High-fashion contemporary particle field & breathing organic contours
 */

document.addEventListener('DOMContentLoaded', () => {
  const canvas = document.getElementById('blandinaCanvas');
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  let width, height;
  let mouse = { x: null, y: null, targetX: null, targetY: null };
  let time = 0;

  function resize() {
    width = canvas.width = canvas.parentElement.offsetWidth;
    height = canvas.height = canvas.parentElement.offsetHeight;
    if (mouse.x === null) {
      mouse.x = width / 2;
      mouse.y = height / 2;
      mouse.targetX = width / 2;
      mouse.targetY = height / 2;
    }
  }

  window.addEventListener('resize', resize);
  resize();

  window.addEventListener('mousemove', (e) => {
    const rect = canvas.getBoundingClientRect();
    mouse.targetX = e.clientX - rect.left;
    mouse.targetY = e.clientY - rect.top;
  });

  // Floating rings / geometric contours (Manifesto mandala aesthetic)
  const ringCount = 14;

  function draw() {
    ctx.clearRect(0, 0, width, height);

    // Smooth mouse lerp
    mouse.x += (mouse.targetX - mouse.x) * 0.05;
    mouse.y += (mouse.targetY - mouse.y) * 0.05;

    time += 0.015;

    const centerX = width / 2;
    const centerY = height / 2;

    // Subtle interactive offset toward mouse
    const offsetX = (mouse.x - centerX) * 0.12;
    const offsetY = (mouse.y - centerY) * 0.12;

    for (let i = 1; i <= ringCount; i++) {
      ctx.beginPath();
      const baseRadius = i * 26 + Math.sin(time + i * 0.25) * 8;
      const points = 64;

      for (let j = 0; j <= points; j++) {
        const angle = (j / points) * Math.PI * 2;
        
        // Organic wave distortion
        const wave = Math.sin(angle * 3 + time * 1.5 + i * 0.4) * 6 +
                     Math.cos(angle * 5 - time) * 4;

        // Interaction distortion near mouse
        const px = centerX + offsetX * (i / ringCount) + Math.cos(angle) * (baseRadius + wave);
        const py = centerY + offsetY * (i / ringCount) + Math.sin(angle) * (baseRadius + wave);

        if (j === 0) {
          ctx.moveTo(px, py);
        } else {
          ctx.lineTo(px, py);
        }
      }

      ctx.closePath();
      // Razor-thin contemporary lines
      const opacity = 0.08 + (i / ringCount) * 0.14;
      ctx.strokeStyle = `rgba(255, 255, 255, ${opacity})`;
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // Subtle floating dust particles (mimicking 35mm film grain in motion)
    for (let p = 0; p < 30; p++) {
      const px = (Math.sin(p * 99 + time * 0.3) * 0.5 + 0.5) * width;
      const py = (Math.cos(p * 45 + time * 0.4) * 0.5 + 0.5) * height;
      ctx.fillStyle = 'rgba(255, 255, 255, 0.15)';
      ctx.fillRect(px, py, 1.5, 1.5);
    }

    requestAnimationFrame(draw);
  }

  draw();
});
