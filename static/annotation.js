(function () {
  const NS = 'http://www.w3.org/2000/svg';
  const clamp = (value, min = 0, max = 1) => Math.max(min, Math.min(max, value));
  const uid = () => 'obj_' + crypto.getRandomValues(new Uint32Array(1))[0].toString(16).padStart(8, '0');

  class DataForgeAnnotator {
    constructor(rootId, options) {
      this.root = document.getElementById(rootId);
      this.svg = this.root.querySelector('.df-overlay');
      this.objects = JSON.parse(JSON.stringify(options.objects || []));
      this.classes = options.classes || [];
      this.lowThreshold = options.lowThreshold || 0.6;
      this.mode = 'select';
      this.selectedId = null;
      this.drag = null;
      this.dirty = false;
      this.showConfidence = true;
      this.keyboardActive = false;
      this.bind();
      this.render();
    }

    bind() {
      this.svg.addEventListener('pointerdown', event => this.pointerDown(event));
      this.svg.addEventListener('pointermove', event => this.pointerMove(event));
      this.svg.addEventListener('pointerup', event => this.pointerUp(event));
      this.svg.addEventListener('pointercancel', event => this.pointerUp(event));
      this.root.addEventListener('mouseenter', () => { this.keyboardActive = true; });
      this.root.addEventListener('mouseleave', () => { this.keyboardActive = false; });
      this.root.addEventListener('focusin', () => { this.keyboardActive = true; });
      this.root.querySelectorAll('[data-mode]').forEach(button => button.addEventListener('click', () => this.setMode(button.dataset.mode)));
      this.root.querySelector('[data-action="delete"]').addEventListener('click', () => this.deleteSelected());
      this.root.querySelector('[data-action="confidence"]').addEventListener('click', () => {
        this.showConfidence = !this.showConfidence;
        this.render();
      });
      this.keyHandler = event => {
        if (!this.keyboardActive || ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) return;
        if (event.ctrlKey && event.key.toLowerCase() === 's') {
          event.preventDefault();
          window.dispatchEvent(new CustomEvent('dataforge-save-request', { detail: { rootId: this.root.id } }));
          return;
        }
        if (event.key.toLowerCase() === 'v') this.setMode('select');
        if (event.key.toLowerCase() === 'b') this.setMode('box');
        if (event.key.toLowerCase() === 'p') window.dispatchEvent(new CustomEvent('dataforge-ai-request', { detail: { rootId: this.root.id } }));
        if (event.key === 'Delete') this.deleteSelected();
        if (event.key === ' ') {
          event.preventDefault();
          window.dispatchEvent(new CustomEvent('dataforge-verify-request', { detail: { rootId: this.root.id } }));
        }
        if (/^[1-9]$/.test(event.key)) this.setClass(Number(event.key) - 1);
      };
      document.addEventListener('keydown', this.keyHandler);
      window.addEventListener('beforeunload', event => {
        if (!this.dirty) return;
        event.preventDefault();
        event.returnValue = '';
      });
    }

    point(event) {
      const rect = this.svg.getBoundingClientRect();
      return { x: clamp((event.clientX - rect.left) / rect.width), y: clamp((event.clientY - rect.top) / rect.height) };
    }

    objectById(id) { return this.objects.find(object => object.id === id); }

    pointerDown(event) {
      if (event.button !== 0) return;
      const point = this.point(event);
      const target = event.target;
      const objectId = target.dataset.objectId;
      if (this.mode === 'box' && !objectId) {
        const classId = this.classes[0]?.id ?? 0;
        const object = { id: uid(), class_id: classId, bbox: [point.x, point.y, point.x, point.y], origin: 'manual', confidence: null, edited: false };
        this.objects.push(object);
        this.selectedId = object.id;
        this.drag = { type: 'create', id: object.id, start: point };
        this.svg.setPointerCapture(event.pointerId);
        this.render();
        return;
      }
      if (objectId) {
        this.selectedId = objectId;
        const object = this.objectById(objectId);
        this.drag = { type: target.dataset.handle ? 'resize' : 'move', handle: target.dataset.handle, id: objectId, start: point, bbox: [...object.bbox] };
        this.svg.setPointerCapture(event.pointerId);
        this.render();
      } else {
        this.selectedId = null;
        this.render();
      }
    }

    pointerMove(event) {
      if (!this.drag) return;
      const point = this.point(event);
      const object = this.objectById(this.drag.id);
      if (!object) return;
      if (this.drag.type === 'create') {
        object.bbox = [Math.min(this.drag.start.x, point.x), Math.min(this.drag.start.y, point.y), Math.max(this.drag.start.x, point.x), Math.max(this.drag.start.y, point.y)];
      } else if (this.drag.type === 'move') {
        const [x1, y1, x2, y2] = this.drag.bbox;
        const width = x2 - x1, height = y2 - y1;
        const dx = point.x - this.drag.start.x, dy = point.y - this.drag.start.y;
        const nx1 = clamp(x1 + dx, 0, 1 - width), ny1 = clamp(y1 + dy, 0, 1 - height);
        object.bbox = [nx1, ny1, nx1 + width, ny1 + height];
      } else {
        let [x1, y1, x2, y2] = this.drag.bbox;
        const handle = this.drag.handle;
        if (handle.includes('w')) x1 = Math.min(point.x, x2 - 0.002);
        if (handle.includes('e')) x2 = Math.max(point.x, x1 + 0.002);
        if (handle.includes('n')) y1 = Math.min(point.y, y2 - 0.002);
        if (handle.includes('s')) y2 = Math.max(point.y, y1 + 0.002);
        object.bbox = [clamp(x1), clamp(y1), clamp(x2), clamp(y2)];
      }
      this.render();
    }

    pointerUp(event) {
      if (!this.drag) return;
      const object = this.objectById(this.drag.id);
      const [x1, y1, x2, y2] = object?.bbox || [0, 0, 0, 0];
      if (!object || x2 - x1 < 0.002 || y2 - y1 < 0.002) {
        this.objects = this.objects.filter(item => item.id !== this.drag.id);
        this.selectedId = null;
      } else {
        if (object.origin === 'ai' && this.drag.type !== 'create') object.edited = true;
        this.markDirty();
      }
      if (this.svg.hasPointerCapture(event.pointerId)) this.svg.releasePointerCapture(event.pointerId);
      this.drag = null;
      this.render();
    }

    setMode(mode) {
      this.mode = mode;
      this.root.querySelectorAll('[data-mode]').forEach(button => button.classList.toggle('active', button.dataset.mode === mode));
      this.svg.style.cursor = mode === 'box' ? 'crosshair' : 'default';
    }

    select(id) { this.selectedId = id; this.render(); }

    setClass(classId) {
      const object = this.objectById(this.selectedId);
      if (!object || !this.classes.some(item => item.id === classId)) return;
      if (object.class_id !== classId) {
        object.class_id = classId;
        if (object.origin === 'ai') object.edited = true;
        this.markDirty();
        this.render();
      }
    }

    deleteSelected() {
      if (!this.selectedId) return;
      this.objects = this.objects.filter(object => object.id !== this.selectedId);
      this.selectedId = null;
      this.markDirty();
      this.render();
    }

    markDirty() {
      this.dirty = true;
      this.root.querySelector('.df-save-state').textContent = '● 有未保存更改';
      this.root.querySelector('.df-save-state').classList.add('df-dirty');
    }

    markSaved() {
      this.dirty = false;
      this.root.querySelector('.df-save-state').textContent = '已保存';
      this.root.querySelector('.df-save-state').classList.remove('df-dirty');
    }

    getState() { return { objects: JSON.parse(JSON.stringify(this.objects)), dirty: this.dirty, selectedId: this.selectedId }; }

    svgElement(name, attrs = {}) {
      const element = document.createElementNS(NS, name);
      Object.entries(attrs).forEach(([key, value]) => element.setAttribute(key, value));
      return element;
    }

    render() {
      this.svg.replaceChildren();
      const rect = this.svg.getBoundingClientRect();
      const hx = rect.width ? 6 / rect.width : .008;
      const hy = rect.height ? 6 / rect.height : .008;
      this.objects.forEach(object => {
        const [x1, y1, x2, y2] = object.bbox;
        const cls = this.classes.find(item => item.id === object.class_id) || { name: '未知类别', color: '#ef4444' };
        const group = this.svgElement('g');
        const classes = ['df-bbox'];
        if (object.id === this.selectedId) classes.push('selected');
        if (object.origin === 'ai' && object.confidence != null && object.confidence < this.lowThreshold) classes.push('ai-low');
        const box = this.svgElement('rect', { x: x1, y: y1, width: x2 - x1, height: y2 - y1, stroke: cls.color, class: classes.join(' '), 'data-object-id': object.id });
        group.appendChild(box);
        const labelText = cls.name + (this.showConfidence && object.confidence != null ? ` ${(object.confidence * 100).toFixed(0)}%` : '');
        const labelWidth = Math.max(0.075, Math.min(0.28, labelText.length * 0.012));
        group.appendChild(this.svgElement('rect', { x: x1, y: Math.max(0, y1 - 0.032), width: labelWidth, height: 0.032, fill: cls.color, class: 'df-label-bg', 'data-object-id': object.id }));
        const text = this.svgElement('text', {
          x: x1 + 0.006,
          y: Math.max(0.022, y1 - 0.008),
          'font-size': 0.022,
          class: 'df-label-text',
        });
        text.textContent = labelText;
        group.appendChild(text);
        if (object.id === this.selectedId) {
          const handles = { nw:[x1,y1], n:[(x1+x2)/2,y1], ne:[x2,y1], e:[x2,(y1+y2)/2], se:[x2,y2], s:[(x1+x2)/2,y2], sw:[x1,y2], w:[x1,(y1+y2)/2] };
          Object.entries(handles).forEach(([name, point]) => group.appendChild(this.svgElement('rect', {
            x: point[0]-hx, y: point[1]-hy, width: hx*2, height: hy*2, class: 'df-handle', 'data-object-id': object.id, 'data-handle': name
          })));
        }
        this.svg.appendChild(group);
      });
      this.renderInspector();
      this.root.querySelector('.df-count').textContent = `${this.objects.length} 个目标`;
    }

    renderInspector() {
      const list = this.root.querySelector('.df-object-list');
      list.replaceChildren();
      if (!this.objects.length) {
        const empty = document.createElement('div');
        empty.className = 'df-object-meta';
        empty.textContent = '暂无目标，可按 B 开始画框。';
        list.appendChild(empty);
      }
      this.objects.forEach((object, index) => {
        const cls = this.classes.find(item => item.id === object.class_id) || { name: '未知类别', color: '#ef4444' };
        const card = document.createElement('div');
        card.className = 'df-object' + (object.id === this.selectedId ? ' selected' : '');
        card.dataset.objectId = object.id;
        const confidence = object.confidence == null ? '' : ` · ${(object.confidence*100).toFixed(1)}%`;
        card.innerHTML = `<div class="df-object-head"><span><i class="df-color-dot" style="background:${cls.color}"></i>${index + 1}. ${cls.name}</span><small>${object.origin === 'ai' ? 'AI' : 'Manual'}</small></div><div class="df-object-meta">${object.edited ? '已人工修正' : '原始'}${confidence}</div>`;
        card.addEventListener('click', () => this.select(object.id));
        list.appendChild(card);
      });
      const select = this.root.querySelector('.df-class-select');
      select.replaceChildren();
      this.classes.forEach(cls => {
        const option = document.createElement('option');
        option.value = String(cls.id); option.textContent = `${cls.id + 1}. ${cls.name}`;
        select.appendChild(option);
      });
      const selected = this.objectById(this.selectedId);
      select.disabled = !selected;
      if (selected) select.value = String(selected.class_id);
      select.onchange = () => this.setClass(Number(select.value));
    }
  }

  window.dataForgeAnnotators = window.dataForgeAnnotators || {};
  window.createDataForgeAnnotator = function (rootId, options) {
    window.dataForgeAnnotators[rootId] = new DataForgeAnnotator(rootId, options);
    return true;
  };
})();
