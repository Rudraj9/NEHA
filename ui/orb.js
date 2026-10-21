/**
 * ui/orb.js
 * ---------
 * Canvas-based visual representation of NEHA's abstract AI presence.
 * 
 * Features:
 * - Central luminous core with layered atmospheric gradients (violet, cyan, rose).
 * - Multi-layered orbital rings with 3D tilt and smooth rotation.
 * - Gentle ambient particle dust field with physics-based drift.
 * - Reactive state animations:
 *   - 'hands_free_off' / 'idle': Serene breathing and slow celestial drift.
 *   - 'waiting_for_wake': Subtle rhythmic breathing with cyan-violet celestial pulse.
 *   - 'acknowledging': High-energy activation pulse wave radiating outward.
 *   - 'listening': Vivid rose-violet responsive listening aura.
 *   - 'recording': High-energy focused speech aura.
 *   - 'transcribing': Cyan-violet swirling rings with rhythmic oscillation.
 *   - 'generating' / 'thinking': Restrained orbit animation with deep violet core.
 *   - 'speaking': Soft rhythmic pulse waves radiating outwards in aquamarine-rose.
 *   - 'follow_up': Anticipatory pulsing cyan-rose rings waiting for follow-up speech.
 *   - 'error': Subdued amber-coral resting state.
 * - Zero external assets (100% self-contained Canvas 2D API).
 * - Honors window resize and 'prefers-reduced-motion'.
 */

(function (root, factory) {
    if (typeof define === 'function' && define.amd) {
        define([], factory);
    } else if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        root.NehaOrb = factory();
    }
}(typeof self !== 'undefined' ? self : this, function () {

    const STATES = {
        hands_free_off: {
            coreHue: 260, // Deep Violet
            accentHue: 195, // Cyan
            pulseSpeed: 0.0012,
            ringSpeed: 0.003,
            intensity: 0.7,
            ringColor1: 'rgba(139, 92, 246, 0.35)',
            ringColor2: 'rgba(6, 182, 212, 0.25)',
            ringColor3: 'rgba(251, 113, 133, 0.18)',
        },
        idle: {
            coreHue: 265,
            accentHue: 190,
            pulseSpeed: 0.0015,
            ringSpeed: 0.004,
            intensity: 0.8,
            ringColor1: 'rgba(139, 92, 246, 0.45)',
            ringColor2: 'rgba(6, 182, 212, 0.35)',
            ringColor3: 'rgba(251, 113, 133, 0.25)',
        },
        waiting_for_wake: {
            coreHue: 270, // Rich Purple-Violet
            accentHue: 185, // Cyan
            pulseSpeed: 0.0022,
            ringSpeed: 0.005,
            intensity: 0.9,
            ringColor1: 'rgba(147, 51, 234, 0.55)',
            ringColor2: 'rgba(6, 182, 212, 0.45)',
            ringColor3: 'rgba(168, 85, 247, 0.3)',
        },
        acknowledging: {
            coreHue: 340, // Rose
            accentHue: 275, // Violet
            pulseSpeed: 0.008,
            ringSpeed: 0.02,
            intensity: 1.45,
            ringColor1: 'rgba(244, 63, 94, 0.95)',
            ringColor2: 'rgba(168, 85, 247, 0.85)',
            ringColor3: 'rgba(251, 113, 133, 0.7)',
        },
        listening: {
            coreHue: 345, // Soft Rose / Crimson
            accentHue: 280, // Violet
            pulseSpeed: 0.005,
            ringSpeed: 0.013,
            intensity: 1.3,
            ringColor1: 'rgba(244, 63, 94, 0.85)',
            ringColor2: 'rgba(168, 85, 247, 0.7)',
            ringColor3: 'rgba(251, 113, 133, 0.55)',
        },
        recording: {
            coreHue: 350, // Crimson Rose
            accentHue: 290,
            pulseSpeed: 0.006,
            ringSpeed: 0.015,
            intensity: 1.35,
            ringColor1: 'rgba(244, 63, 94, 0.9)',
            ringColor2: 'rgba(217, 70, 239, 0.75)',
            ringColor3: 'rgba(251, 113, 133, 0.6)',
        },
        transcribing: {
            coreHue: 190, // Cyan
            accentHue: 270, // Violet
            pulseSpeed: 0.0055,
            ringSpeed: 0.016,
            intensity: 1.2,
            ringColor1: 'rgba(6, 182, 212, 0.8)',
            ringColor2: 'rgba(139, 92, 246, 0.7)',
            ringColor3: 'rgba(34, 211, 238, 0.5)',
        },
        thinking: {
            coreHue: 275, // Rich Violet
            accentHue: 185, // Cyan
            pulseSpeed: 0.004,
            ringSpeed: 0.014,
            intensity: 1.15,
            ringColor1: 'rgba(168, 85, 247, 0.75)',
            ringColor2: 'rgba(6, 182, 212, 0.65)',
            ringColor3: 'rgba(244, 63, 94, 0.4)',
        },
        generating: {
            coreHue: 275,
            accentHue: 185,
            pulseSpeed: 0.0045,
            ringSpeed: 0.015,
            intensity: 1.15,
            ringColor1: 'rgba(168, 85, 247, 0.75)',
            ringColor2: 'rgba(6, 182, 212, 0.65)',
            ringColor3: 'rgba(244, 63, 94, 0.4)',
        },
        speaking: {
            coreHue: 185, // Cyan / Aquamarine
            accentHue: 330, // Rose
            pulseSpeed: 0.0038,
            ringSpeed: 0.009,
            intensity: 1.2,
            ringColor1: 'rgba(34, 211, 238, 0.75)',
            ringColor2: 'rgba(244, 63, 94, 0.6)',
            ringColor3: 'rgba(168, 85, 247, 0.5)',
        },
        follow_up: {
            coreHue: 210, // Electric Blue
            accentHue: 330, // Rose
            pulseSpeed: 0.004,
            ringSpeed: 0.01,
            intensity: 1.1,
            ringColor1: 'rgba(56, 189, 248, 0.75)',
            ringColor2: 'rgba(244, 63, 94, 0.55)',
            ringColor3: 'rgba(147, 51, 234, 0.45)',
        },
        error: {
            coreHue: 15, // Amber / Coral
            accentHue: 350,
            pulseSpeed: 0.001,
            ringSpeed: 0.002,
            intensity: 0.7,
            ringColor1: 'rgba(245, 158, 11, 0.55)',
            ringColor2: 'rgba(239, 68, 68, 0.45)',
            ringColor3: 'rgba(245, 158, 11, 0.25)',
        }
    };

    class NehaOrb {
        constructor(canvasId) {
            this.canvas = document.getElementById(canvasId);
            if (!this.canvas) return;

            this.ctx = this.canvas.getContext('2d');
            this.state = 'hands_free_off';
            this.targetState = 'hands_free_off';
            this.angle1 = 0;
            this.angle2 = Math.PI / 3;
            this.angle3 = Math.PI * 0.7;
            this.pulseTime = 0;
            this.particles = [];
            this.numParticles = 36;
            this.dpr = window.devicePixelRatio || 1;
            this.reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

            // Activation pulse waves
            this.activationWaves = [];

            this.initParticles();
            this.resize();

            window.addEventListener('resize', () => this.resize());
            this.animate = this.animate.bind(this);
            requestAnimationFrame(this.animate);
        }

        resize() {
            if (!this.canvas) return;
            const rect = this.canvas.getBoundingClientRect();
            this.width = rect.width;
            this.height = rect.height;
            this.canvas.width = this.width * this.dpr;
            this.canvas.height = this.height * this.dpr;
            this.ctx.scale(this.dpr, this.dpr);
            this.centerX = this.width / 2;
            this.centerY = this.height / 2;
            this.baseRadius = Math.min(this.width, this.height) * 0.23;
        }

        initParticles() {
            this.particles = [];
            for (let i = 0; i < this.numParticles; i++) {
                this.particles.push({
                    x: (Math.random() - 0.5) * 260,
                    y: (Math.random() - 0.5) * 260,
                    radius: Math.random() * 1.8 + 0.6,
                    speedX: (Math.random() - 0.5) * 0.35,
                    speedY: (Math.random() - 0.5) * 0.35,
                    alpha: Math.random() * 0.55 + 0.25,
                    hue: Math.random() > 0.5 ? 260 : 190
                });
            }
        }

        triggerActivationPulse() {
            this.activationWaves.push({
                radius: this.baseRadius * 0.8,
                maxRadius: this.baseRadius * 2.8,
                alpha: 0.9,
                speed: 3.5,
                hue: 340,
            });
        }

        setState(newState) {
            const mapped = STATES[newState] ? newState : (newState === 'reviewing' ? 'idle' : 'hands_free_off');
            if (this.state !== mapped) {
                if (mapped === 'acknowledging') {
                    this.triggerActivationPulse();
                }
                this.state = mapped;
            }
        }

        animate(timestamp) {
            if (!this.ctx) return;
            this.ctx.clearRect(0, 0, this.width, this.height);

            const cfg = STATES[this.state] || STATES.hands_free_off;
            const motionFactor = this.reducedMotion ? 0.3 : 1.0;

            // Pulse calculations
            this.pulseTime += cfg.pulseSpeed * motionFactor * 16.6;
            const pulse = Math.sin(this.pulseTime) * 0.08 * cfg.intensity;
            const currentRadius = this.baseRadius * (1 + pulse);

            // Ring rotation
            this.angle1 += cfg.ringSpeed * motionFactor;
            this.angle2 -= cfg.ringSpeed * 0.85 * motionFactor;
            this.angle3 += cfg.ringSpeed * 0.6 * motionFactor;

            // 1. Draw Floating Particles
            this.drawParticles(motionFactor);

            // 2. Draw Outer Glowing Atmosphere
            this.drawAtmosphere(currentRadius, cfg);

            // 3. Draw Activation Pulse Waves
            this.drawActivationWaves(motionFactor);

            // 4. Draw Orbital Rings
            this.drawOrbitalRings(currentRadius, cfg);

            // 5. Draw Inner Luminous Core
            this.drawCore(currentRadius, cfg);

            requestAnimationFrame(this.animate);
        }

        triggerActivationPulse() {
            this.activationWaves.push({
                radius: this.baseRadius * 0.8,
                maxRadius: this.baseRadius * 2.8,
                alpha: 0.85,
                speed: 3.2,
                hue: 340,
            });
        }

        drawActivationWaves(motionFactor) {
            const ctx = this.ctx;
            for (let i = this.activationWaves.length - 1; i >= 0; i--) {
                const wave = this.activationWaves[i];
                wave.radius += wave.speed * motionFactor;
                wave.alpha *= 0.96;

                ctx.save();
                ctx.beginPath();
                ctx.arc(this.centerX, this.centerY, wave.radius, 0, Math.PI * 2);
                ctx.strokeStyle = `hsla(${wave.hue}, 90%, 70%, ${wave.alpha})`;
                ctx.lineWidth = 2.5;
                ctx.shadowColor = `hsla(${wave.hue}, 90%, 65%, ${wave.alpha})`;
                ctx.shadowBlur = 16;
                ctx.stroke();
                ctx.restore();

                if (wave.radius >= wave.maxRadius || wave.alpha <= 0.02) {
                    this.activationWaves.splice(i, 1);
                }
            }
        }

        drawAtmosphere(radius, cfg) {
            const ctx = this.ctx;
            const glowRadius = radius * 2.3;
            const grad = ctx.createRadialGradient(
                this.centerX, this.centerY, radius * 0.3,
                this.centerX, this.centerY, glowRadius
            );

            grad.addColorStop(0, `hsla(${cfg.coreHue}, 90%, 65%, ${0.30 * cfg.intensity})`);
            grad.addColorStop(0.45, `hsla(${cfg.accentHue}, 85%, 60%, ${0.15 * cfg.intensity})`);
            grad.addColorStop(1, 'rgba(7, 11, 20, 0)');

            ctx.save();
            ctx.fillStyle = grad;
            ctx.beginPath();
            ctx.arc(this.centerX, this.centerY, glowRadius, 0, Math.PI * 2);
            ctx.fill();
            ctx.restore();
        }

        drawOrbitalRings(radius, cfg) {
            const ctx = this.ctx;
            const cx = this.centerX;
            const cy = this.centerY;

            // Ring 1 (Tilted Ellipse)
            ctx.save();
            ctx.translate(cx, cy);
            ctx.rotate(0.45);
            ctx.beginPath();
            ctx.ellipse(0, 0, radius * 1.55, radius * 0.65, this.angle1, 0, Math.PI * 2);
            ctx.strokeStyle = cfg.ringColor1;
            ctx.lineWidth = 1.8;
            ctx.shadowColor = cfg.ringColor1;
            ctx.shadowBlur = 12;
            ctx.stroke();

            // Ring 1 Node/Satellite
            const nodeX = Math.cos(this.angle1) * radius * 1.55;
            const nodeY = Math.sin(this.angle1) * radius * 0.65;
            ctx.beginPath();
            ctx.arc(nodeX, nodeY, 3.0, 0, Math.PI * 2);
            ctx.fillStyle = '#ffffff';
            ctx.shadowColor = '#38bdf8';
            ctx.shadowBlur = 14;
            ctx.fill();
            ctx.restore();

            // Ring 2 (Opposite Tilt)
            ctx.save();
            ctx.translate(cx, cy);
            ctx.rotate(-0.65);
            ctx.beginPath();
            ctx.ellipse(0, 0, radius * 1.75, radius * 0.75, this.angle2, 0, Math.PI * 2);
            ctx.strokeStyle = cfg.ringColor2;
            ctx.lineWidth = 1.4;
            ctx.setLineDash([6, 8]);
            ctx.stroke();
            ctx.setLineDash([]);
            ctx.restore();

            // Ring 3 (Outer Circular Orbit with Gentle Waves)
            ctx.save();
            ctx.translate(cx, cy);
            ctx.rotate(this.angle3);
            ctx.beginPath();
            ctx.arc(0, 0, radius * 1.35, 0, Math.PI * 2);
            ctx.strokeStyle = cfg.ringColor3;
            ctx.lineWidth = 1.1;
            ctx.stroke();
            ctx.restore();
        }

        drawCore(radius, cfg) {
            const ctx = this.ctx;
            const cx = this.centerX;
            const cy = this.centerY;

            // Multi-layered glass core
            const coreGrad = ctx.createRadialGradient(
                cx - radius * 0.25, cy - radius * 0.25, radius * 0.1,
                cx, cy, radius
            );

            coreGrad.addColorStop(0, '#ffffff');
            coreGrad.addColorStop(0.2, `hsl(${cfg.accentHue}, 90%, 80%)`);
            coreGrad.addColorStop(0.55, `hsl(${cfg.coreHue}, 85%, 65%)`);
            coreGrad.addColorStop(0.9, `hsl(${cfg.coreHue + 20}, 90%, 35%)`);
            coreGrad.addColorStop(1, 'rgba(15, 23, 42, 0.4)');

            ctx.save();
            ctx.beginPath();
            ctx.arc(cx, cy, radius, 0, Math.PI * 2);
            ctx.fillStyle = coreGrad;
            ctx.shadowColor = `hsl(${cfg.coreHue}, 90%, 70%)`;
            ctx.shadowBlur = 26 * cfg.intensity;
            ctx.fill();

            // Inner specular crescent highlight
            ctx.beginPath();
            ctx.ellipse(cx - radius * 0.35, cy - radius * 0.35, radius * 0.35, radius * 0.2, Math.PI / 4, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(255, 255, 255, 0.38)';
            ctx.fill();

            ctx.restore();
        }

        drawParticles(motionFactor) {
            const ctx = this.ctx;
            const cx = this.centerX;
            const cy = this.centerY;
            const boundary = this.baseRadius * 2.4;

            ctx.save();
            for (let p of this.particles) {
                p.x += p.speedX * motionFactor;
                p.y += p.speedY * motionFactor;

                // Wrap boundary
                const dist = Math.hypot(p.x, p.y);
                if (dist > boundary) {
                    p.x = -p.x * 0.9;
                    p.y = -p.y * 0.9;
                }

                ctx.beginPath();
                ctx.arc(cx + p.x, cy + p.y, p.radius, 0, Math.PI * 2);
                ctx.fillStyle = `hsla(${p.hue}, 85%, 75%, ${p.alpha})`;
                ctx.shadowColor = `hsla(${p.hue}, 90%, 70%, ${p.alpha})`;
                ctx.shadowBlur = 6;
                ctx.fill();
            }
            ctx.restore();
        }
    }

    return NehaOrb;
}));
