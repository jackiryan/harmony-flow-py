import 'ol/ol.css';
import Map from 'ol/Map.js';
import View from 'ol/View.js';
import TileLayer from 'ol/layer/Tile.js';
import OSM from 'ol/source/OSM.js';
import Flow from 'ol/layer/Flow.js';
import DataTileSource from 'ol/source/DataTile.js';
import { createForProjection, wrapX } from 'ol/tilegrid.js'; 
import { get as getProjection } from 'ol/proj.js'; 
import './style.css';
import { 
    HarmonyClient, 
    OSCAR_COLLECTIONS, 
    VARIABLE_TYPES,
    isDateInRange,
    type CollectionConfig,
    type VariableConfig 
} from './harmony-api.js';

// 1. Load the PNG
interface CurrentData {
    data: Uint8ClampedArray;
    width: number;
    height: number;
    lon0: number; // center longitude of pixel 0 (degrees); accounts for non-zero west edge
}

async function fetchImageBlob(url: string): Promise<string> {
    const headers: Record<string, string> = {};
    const token = harmonyClient?.getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const response = await fetch(url, { headers });
    if (!response.ok) throw new Error(`Image fetch failed: ${response.status}`);
    const blob = await response.blob();
    return URL.createObjectURL(blob);
}

async function loadImageData(src: string, lon0 = 0): Promise<CurrentData> {
    // External URLs need auth header and can't be loaded directly by <img>
    const imageSrc = src.startsWith('http') ? await fetchImageBlob(src) : src;
    return new Promise((resolve, reject) => {
        const image = new Image();
        image.onload = () => {
            const canvas = document.createElement('canvas');
            canvas.width = image.width;
            canvas.height = image.height;
            const context = canvas.getContext('2d');
            if (!context) {
                reject(new Error('Failed to get 2d context'));
                return;
            }
            context.drawImage(image, 0, 0);
            resolve({
                data: context.getImageData(0, 0, image.width, image.height).data,
                width: image.width,
                height: image.height,
                lon0,
            });
            if (imageSrc !== src) URL.revokeObjectURL(imageSrc);
        };
        image.onerror = () => reject(new Error(`failed to load image: ${src}`));
        image.src = imageSrc;
    });
}

// Global state
let currentData: Promise<CurrentData> = loadImageData('/oscar_currents_interim_2020-01-01_u_v.png');
let currentCollection: CollectionConfig = OSCAR_COLLECTIONS.interim;
let currentVariables: VariableConfig = VARIABLE_TYPES['u_v'];
let forceApiMode = false; // Toggle to force using Harmony API instead of static files
let currentDateStr = '2020-01-01'; // Tracks the currently displayed date
const harmonyClient = new HarmonyClient('sit');

// 2. Interpolation Math
function bilinearInterpolation(
    xAlong: number, yAlong: number,
    v11: number, v21: number, v12: number, v22: number
): number {
    return (1 - xAlong) * (1 - yAlong) * v11 +
           xAlong * (1 - yAlong) * v21 +
           (1 - xAlong) * yAlong * v12 +
           xAlong * yAlong * v22;
}

function interpolatePixels(
    xAlong: number, yAlong: number,
    p11: number[], p21: number[], p12: number[], p22: number[]
): number[] {
    return p11.map((_, i) =>
        bilinearInterpolation(xAlong, yAlong, p11[i], p21[i], p12[i], p22[i])
    );
}

// 3. Grid Setup
const dataTileProjection = getProjection('EPSG:4326')!;
const dataTileGrid = createForProjection(dataTileProjection, undefined, 256);
const dataTileSize = 256;
const inputBands = 4;
const dataBands = 3;

let minU = -2.92, maxU = 2.93, deltaU = maxU - minU;
let minV = -2.81, maxV = 2.69, deltaV = maxV - minV;

// 4. Data Loader
const currents = new DataTileSource({
    projection: 'EPSG:4326',
    tileGrid: dataTileGrid,
    transition: 0,
    wrapX: true, 
    async loader(z: number, x: number, y: number): Promise<Float32Array> {
        const { data: inputData, width: inputWidth, height: inputHeight, lon0 } = await currentData;
        const tileCoord = wrapX(dataTileGrid, [z, x, y], dataTileProjection);
        const extent = dataTileGrid.getTileCoordExtent(tileCoord)!;
        const resolution = dataTileGrid.getResolution(z);
        const data = new Float32Array(dataTileSize * dataTileSize * dataBands);
        
        for (let row = 0; row < dataTileSize; ++row) {
            let offset = row * dataTileSize * dataBands;
            const lat = extent[3] - row * resolution; // Directly in Latitude
            for (let col = 0; col < dataTileSize; ++col) {
                const rawLon = extent[0] + col * resolution; // Directly in Longitude
                
                const lon360 = ((rawLon % 360) + 360) % 360; 
                const degreesPerPixelX = 360 / inputWidth;
                const degreesPerPixelY = 180 / inputHeight;

                // Adjust for non-zero west edge: lon0 is the center longitude of pixel 0
                const adjustedLon = ((lon360 - lon0) % 360 + 360) % 360;
                const xPos = adjustedLon / degreesPerPixelX;
                const yPos = (90 - lat) / degreesPerPixelY;

                let x1 = Math.floor(xPos), x2 = Math.ceil(xPos);
                const xAlong = xPos - x1;
                if (x1 < 0) x1 += inputWidth;
                if (x2 >= inputWidth) x2 -= inputWidth;

                let y1 = Math.floor(yPos), y2 = Math.ceil(yPos);
                const yAlong = yPos - y1;
                if (y1 < 0) y1 = 0;
                if (y2 >= inputHeight) y2 = inputHeight - 1;

                const corners = [[x1, y1], [x2, y1], [x1, y2], [x2, y2]];
                const pixels = corners.map(([cx, cy]) => {
                    const idx = (cy * inputWidth + cx) * inputBands;
                    return [inputData[idx], inputData[idx + 1]];
                });

                const interpolated = interpolatePixels(xAlong, yAlong, pixels[0], pixels[1], pixels[2], pixels[3]);
                
                data[offset] = minU + (deltaU * interpolated[0]) / 255;
                data[offset + 1] = minV + (deltaV * interpolated[1]) / 255;
                offset += dataBands;
            }
        }
        return data;
    },
});

// 5. Styling
const maxSpeed = 2;
const viridisColors = ['#440154', '#414487', '#2a788e', '#22a884', '#7ad151', '#fde725'];
const colorStops: any[] = [];
for (let i = 0; i < viridisColors.length; ++i) {
    colorStops.push((i * maxSpeed) / (viridisColors.length - 1));
    colorStops.push(viridisColors[i]);
}

const flowColorExpression: any = [
    'case',
    ['>', ['get', 'speed'], maxSpeed], 
    'rgba(0, 0, 0, 0)',         
    ['interpolate', ['linear'], ['get', 'speed'], ...colorStops]
];

function makeFlowLayer(): Flow {
    return new Flow({
        source: currents,
        maxSpeed: maxSpeed,
        style: { color: flowColorExpression },
    });
}

// 6. Map Initialization
function getViewFromURL(): { center: [number, number]; zoom: number } {
    const params = new URLSearchParams(window.location.search);
    const cx = parseFloat(params.get('cx') ?? '');
    const cy = parseFloat(params.get('cy') ?? '');
    const z  = parseFloat(params.get('z')  ?? '');
    const center: [number, number] = (isFinite(cx) && isFinite(cy)) ? [cx, cy] : [0, 0];
    const zoom = isFinite(z) ? z : 2;
    return { center, zoom };
}

const { center: initCenter, zoom: initZoom } = getViewFromURL();
const map = new Map({
    target: 'map',
    layers: [
        new TileLayer({ source: new OSM() }),
    ],
    view: new View({ 
        center: initCenter, 
        zoom: initZoom,
        projection: 'EPSG:4326' 
    }),
});

let flowLayer = makeFlowLayer();
flowLayer.setOpacity(0);
map.addLayer(flowLayer);

// 7. Handle Flow Layer Visibility During Drag
let warmUpId: number | null = null;

currentData.then(() => {
    let frames = 0;
    const warmUp = () => {
        if (++frames < 10) {
            warmUpId = requestAnimationFrame(warmUp);
        } else {
            flowLayer.setOpacity(1);
            warmUpId = null;
        }
    };
    warmUpId = requestAnimationFrame(warmUp);
});

map.on('movestart', () => {
    if (warmUpId !== null) {
        cancelAnimationFrame(warmUpId);
        warmUpId = null;
    }
    flowLayer.setOpacity(0);
});

map.on('moveend', () => {
    // Persist zoom + center to URL without adding a browser history entry
    const view = map.getView();
    const [cx, cy] = view.getCenter() as [number, number];
    const z = view.getZoom()!;
    const params = new URLSearchParams(window.location.search);
    params.set('cx', cx.toFixed(4));
    params.set('cy', cy.toFixed(4));
    params.set('z',  z.toFixed(3));
    history.replaceState(null, '', `?${params.toString()}`);

    const oldLayer = flowLayer;
    
    flowLayer = makeFlowLayer();
    flowLayer.setOpacity(0); 
    map.addLayer(flowLayer);

    let frames = 0;
    const warmUp = () => {
        frames++;
        if (frames < 10) {
            warmUpId = requestAnimationFrame(warmUp);
        } else {
            flowLayer.setOpacity(1);
            map.removeLayer(oldLayer);  
            warmUpId = null;
        }
    };
    warmUpId = requestAnimationFrame(warmUp);
});

// 8. Status Indicator
function showStatus(title: string, message: string, progress?: number): HTMLElement {
    let statusEl = document.querySelector('.status-indicator') as HTMLElement;
    
    if (!statusEl) {
        statusEl = document.createElement('div');
        statusEl.className = 'status-indicator';
        document.getElementById('map')!.appendChild(statusEl);
    }
    
    const progressBar = progress !== undefined 
        ? `<div class="status-progress"><div class="status-progress-bar" style="width: ${progress}%"></div></div>`
        : '';
    
    statusEl.innerHTML = `
        <div class="status-title">${title}</div>
        <div class="status-message">${message}</div>
        ${progressBar}
    `;
    
    return statusEl;
}

function hideStatus(): void {
    const statusEl = document.querySelector('.status-indicator');
    if (statusEl) {
        statusEl.remove();
    }
}

// 9. Dynamic PNG Loading
async function loadPNGForDate(dateStr: string): Promise<{ pngUrl: string; lon0: number }> {
    const { pngUrl, lon0 } = await harmonyClient.generateTexture(
        currentCollection.id,
        currentCollection.shortname,
        dateStr,
        currentVariables.variables,
        (progress, message) => {
            showStatus('Generating Texture', message, progress);
        }
    );
    return { pngUrl, lon0 };
}

// 10. Date Switching with Dynamic Loading
async function switchDate(dateStr: string): Promise<void> {
    currentDateStr = dateStr;
    try {
        // Check if we should use API mode or static files
        if (forceApiMode) {
            // Check date is within the selected collection's temporal range
            if (!isDateInRange(dateStr, currentCollection)) {
                const end = currentCollection.endDate ?? 'present';
                throw new Error(
                    `${currentCollection.name} has no data for ${dateStr}. ` +
                    `Coverage: ${currentCollection.startDate} → ${end}.`
                );
            }
            // Force API mode: skip static file check
            showStatus('Loading Data', 'Checking cache...', 0);
            const { pngUrl, lon0 } = await loadPNGForDate(dateStr);
            currentData = loadImageData(pngUrl, lon0);
            console.log('Current data:', currentData);
        } else {
            // Try to load from local static files first (for development)
            const staticUrl = `/oscar_currents_nrt_${dateStr}_${currentVariables.variables.join('_')}.png`;
            
            try {
                const response = await fetch(staticUrl, { method: 'HEAD' });
                if (response.ok) {
                    // Static file exists, use it
                    currentData = loadImageData(staticUrl);
                } else {
                    throw new Error('Static file not found');
                }
            } catch {
                // Fall back to dynamic generation
                showStatus('Loading Data', 'Checking cache...', 0);
                const { pngUrl, lon0 } = await loadPNGForDate(dateStr);
                currentData = loadImageData(pngUrl, lon0);
            }
        }
        
        hideStatus();
        
        currents.clear();
        if (warmUpId !== null) {
            cancelAnimationFrame(warmUpId);
            warmUpId = null;
        }
        const oldLayer = flowLayer;
        flowLayer = makeFlowLayer();
        flowLayer.setOpacity(0);
        map.addLayer(flowLayer);
        let frames = 0;
        const warmUp = () => {
            if (++frames < 10) {
                warmUpId = requestAnimationFrame(warmUp);
            } else {
                flowLayer.setOpacity(1);
                map.removeLayer(oldLayer);
                warmUpId = null;
            }
        };
        warmUpId = requestAnimationFrame(warmUp);
    } catch (error) {
        console.error('Error switching date:', error);
        showStatus('Error', `Failed to load data: ${error instanceof Error ? error.message : 'Unknown error'}`);
        setTimeout(hideStatus, 5000);
    }
}

// 11. Earthdata Bearer Token Dialog
function promptToken(): Promise<string | null> {
    return new Promise((resolve) => {
        const overlay = document.createElement('div');
        overlay.className = 'credentials-overlay';

        overlay.innerHTML = `
            <div class="credentials-dialog">
                <div class="credentials-title">Earthdata Bearer Token</div>
                <div class="credentials-subtitle">
                    Log in to <a href="https://uat.urs.earthdata.nasa.gov" target="_blank" class="credentials-link">uat.urs.earthdata.nasa.gov</a>,
                    go to <strong>Profile &rarr; User Tokens</strong>
                    (<code>/users/&lt;username&gt;/user_tokens</code>), generate a token, and paste it below.
                </div>
                <div class="credentials-field">
                    <label class="credentials-label">Bearer Token</label>
                    <input type="password" class="credentials-input" id="cred-token" placeholder="Paste your Earthdata token here" />
                    <div id="cred-error" style="color:#ff6b6b;font-size:0.75rem;margin-top:4px;display:none;">Invalid token — must be a JWT (starts with eyJ…). Generate one at the link above.</div>
                </div>
                <div class="credentials-actions">
                    <button class="credentials-btn credentials-btn-cancel" id="cred-cancel">Cancel</button>
                    <button class="credentials-btn credentials-btn-submit" id="cred-submit">Connect</button>
                </div>
            </div>
        `;

        document.body.appendChild(overlay);

        const tokenInput = overlay.querySelector('#cred-token') as HTMLInputElement;
        tokenInput.focus();

        const finish = (token: string | null) => {
            overlay.remove();
            resolve(token);
        };

        const errorMsg = overlay.querySelector('#cred-error') as HTMLElement;
        const isValidToken = (t: string) => t.startsWith('eyJ') && t.split('.').length === 3;

        const trySubmit = () => {
            const token = tokenInput.value.trim();
            if (!token) return;
            if (!isValidToken(token)) {
                errorMsg.style.display = 'block';
                tokenInput.style.borderColor = '#ff6b6b';
                return;
            }
            finish(token);
        };

        tokenInput.addEventListener('input', () => {
            errorMsg.style.display = 'none';
            tokenInput.style.borderColor = '';
        });

        overlay.querySelector('#cred-cancel')!.addEventListener('click', () => finish(null));
        overlay.querySelector('#cred-submit')!.addEventListener('click', trySubmit);
        tokenInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') trySubmit(); });
    });
}

// 12. UI Controls
function buildControls(): void {
    const container = document.createElement('div');
    container.className = 'controls-container';
    
    // Collection selector
    const collectionGroup = document.createElement('div');
    collectionGroup.className = 'control-group';
    
    const collectionLabel = document.createElement('label');
    collectionLabel.className = 'control-label';
    collectionLabel.textContent = 'Collection';
    
    const collectionSelect = document.createElement('select');
    collectionSelect.className = 'control-select';
    
    Object.entries(OSCAR_COLLECTIONS).forEach(([key, config]) => {
        const option = document.createElement('option');
        option.value = key;
        option.textContent = config.name;
        if (config.id === currentCollection.id) {
            option.selected = true;
        }
        collectionSelect.appendChild(option);
    });
    
    collectionSelect.addEventListener('change', async (e) => {
        const key = (e.target as HTMLSelectElement).value;
        currentCollection = OSCAR_COLLECTIONS[key as keyof typeof OSCAR_COLLECTIONS];
        console.log('Collection changed to:', currentCollection.name);
        buildNavigator(generateDatesForCollection(currentCollection));
    });
    
    collectionGroup.appendChild(collectionLabel);
    collectionGroup.appendChild(collectionSelect);
    
    // Variable selector
    const variableGroup = document.createElement('div');
    variableGroup.className = 'control-group';
    
    const variableLabel = document.createElement('label');
    variableLabel.className = 'control-label';
    variableLabel.textContent = 'Variables';
    
    const variableSelect = document.createElement('select');
    variableSelect.className = 'control-select';
    
    Object.entries(VARIABLE_TYPES).forEach(([key, config]) => {
        const option = document.createElement('option');
        option.value = key;
        option.textContent = config.name;
        if (config.variables.join('_') === currentVariables.variables.join('_')) {
            option.selected = true;
        }
        variableSelect.appendChild(option);
    });
    
    variableSelect.addEventListener('change', async (e) => {
        const key = (e.target as HTMLSelectElement).value;
        currentVariables = VARIABLE_TYPES[key as keyof typeof VARIABLE_TYPES];
        console.log('Variables changed to:', currentVariables.name);
        switchDate(currentDateStr);
    });
    
    variableGroup.appendChild(variableLabel);
    variableGroup.appendChild(variableSelect);
    
    // API Mode toggle
    const apiModeGroup = document.createElement('div');
    apiModeGroup.className = 'control-group';
    
    const apiModeLabel = document.createElement('label');
    apiModeLabel.className = 'control-label';
    apiModeLabel.textContent = 'Data Source';
    
    const apiModeToggle = document.createElement('div');
    apiModeToggle.className = 'toggle-container';
    
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.id = 'api-mode-toggle';
    checkbox.className = 'toggle-checkbox';
    checkbox.checked = forceApiMode;
    
    const toggleLabel = document.createElement('label');
    toggleLabel.htmlFor = 'api-mode-toggle';
    toggleLabel.className = 'toggle-label';
    toggleLabel.innerHTML = `
        <span class="toggle-text">${forceApiMode ? 'Harmony API' : 'Static Files'}</span>
        <span class="toggle-switch"></span>
    `;
    
    checkbox.addEventListener('change', async (e) => {
        const enabled = (e.target as HTMLInputElement).checked;

        if (enabled && !harmonyClient.hasToken()) {
            const token = await promptToken();
            if (!token) {
                checkbox.checked = false;
                return;
            }
            harmonyClient.setToken(token);
        }

        forceApiMode = enabled;
        const text = toggleLabel.querySelector('.toggle-text');
        if (text) {
            text.textContent = forceApiMode ? 'Harmony API' : 'Static Files';
        }
        console.log('API mode:', forceApiMode ? 'enabled' : 'disabled');
        if (forceApiMode) {
            switchDate(currentDateStr);
        }
    });
    
    apiModeToggle.appendChild(checkbox);
    apiModeToggle.appendChild(toggleLabel);
    apiModeGroup.appendChild(apiModeLabel);
    apiModeGroup.appendChild(apiModeToggle);
    
    container.appendChild(collectionGroup);
    container.appendChild(variableGroup);
    container.appendChild(apiModeGroup);
    document.getElementById('map')!.appendChild(container);
}

// 12. Time Navigator
interface OscarMetadata { dates: string[] }

interface URLSyncConfig {
    year?: number;
    month?: number;
    day?: number;
}

interface AppState {
    currentYear: number;
    currentMonth: number;
    currentDay: number;
}

const DEFAULT_STATE: AppState = {
    currentYear: 2020,
    currentMonth: 1,
    currentDay: 1,
};

function dateStrToState(dateStr: string): AppState {
    const [year, month, day] = dateStr.split('-').map(Number);
    return { currentYear: year, currentMonth: month, currentDay: day };
}

function stateToDateStr(state: AppState): string {
    const mm = String(state.currentMonth).padStart(2, '0');
    const dd = String(state.currentDay).padStart(2, '0');
    return `${state.currentYear}-${mm}-${dd}`;
}

function getStateFromURL(): AppState {
    const params = new URLSearchParams(window.location.search);
    const year  = Number(params.get('year'))  || DEFAULT_STATE.currentYear;
    const month = Number(params.get('month')) || DEFAULT_STATE.currentMonth;
    const day   = Number(params.get('day'))   || DEFAULT_STATE.currentDay;
    return { currentYear: year, currentMonth: month, currentDay: day };
}

function pushStateToURL(config: URLSyncConfig): void {
    const params = new URLSearchParams(window.location.search);
    if (config.year  !== undefined) params.set('year',  String(config.year));
    if (config.month !== undefined) params.set('month', String(config.month));
    if (config.day   !== undefined) params.set('day',   String(config.day));
    history.pushState(null, '', `?${params.toString()}`);
}
// --- end URL state sync ---

const MONTH_NAMES = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
];

function formatDateLabel(dateStr: string): string {
    const [year, month, day] = dateStr.split('-').map(Number);
    return `${MONTH_NAMES[month - 1]} ${day}, ${year}`;
}

function generateDatesForCollection(collection: CollectionConfig): string[] {
    const dates: string[] = [];
    const end = collection.endDate ?? new Date().toISOString().slice(0, 10);
    const cur = new Date(collection.startDate + 'T12:00:00Z');
    const endDate = new Date(end + 'T12:00:00Z');
    while (cur <= endDate) {
        dates.push(cur.toISOString().slice(0, 10));
        cur.setUTCDate(cur.getUTCDate() + 1);
    }
    return dates;
}

function buildNavigator(dates: string[]): void {
    // Tear down existing navigator if present
    document.querySelector('.time-navigator-container')?.remove();

    const urlParams = new URLSearchParams(window.location.search);
    const hasURLDate = urlParams.has('year') || urlParams.has('month') || urlParams.has('day');
    const initialState = getStateFromURL();
    const initialDateStr = stateToDateStr(initialState);
    let idx = dates.indexOf(initialDateStr);
    let isLoading = false;

    // showingStatic: true when displaying the pre-generated default outside the collection range.
    // idx is set to dates.length (one past the end) so ◀ naturally navigates to dates[dates.length-1].
    let showingStatic = false;

    if (idx < 0) {
        // Date not in collection range
        idx = initialDateStr > dates[dates.length - 1] ? dates.length : 0;
        if (!hasURLDate) {
            // No explicit URL date: show static default, leave currentData untouched
            showingStatic = true;
        } else {
            // URL had an out-of-range date: clamp to nearest boundary and load it
            idx = Math.min(idx, dates.length - 1);
            switchDate(dates[idx]);
        }
    } else {
        if (idx !== 0 || initialDateStr !== dates[0]) {
            switchDate(dates[idx]);
        }
    }

    const container = document.createElement('div');
    container.className = 'time-navigator-container';

    const nav = document.createElement('div');
    nav.className = 'time-navigator';

    const prevBtn = document.createElement('button');
    prevBtn.className = 'time-nav-button';
    prevBtn.textContent = '◀';
    prevBtn.setAttribute('aria-label', 'Previous date');

    const displayLabel = document.createElement('span');
    displayLabel.className = 'time-display time-display-clickable';
    displayLabel.title = 'Click to jump to a date';

    const dateInput = document.createElement('input');
    dateInput.type = 'date';
    dateInput.className = 'time-date-input';
    dateInput.min = dates[0];
    dateInput.max = dates[dates.length - 1];
    dateInput.style.display = 'none';

    const nextBtn = document.createElement('button');
    nextBtn.className = 'time-nav-button';
    nextBtn.textContent = '▶';
    nextBtn.setAttribute('aria-label', 'Next date');

    function sync(): void {
        const displayDate = showingStatic ? currentDateStr : dates[idx];
        displayLabel.textContent = formatDateLabel(displayDate);
        dateInput.value = displayDate;
        prevBtn.disabled = isLoading || idx <= 0;
        nextBtn.disabled = isLoading || idx >= dates.length - 1;
        nav.classList.toggle('loading', isLoading);
    }

    function findNearestIdx(targetDate: string): number {
        if (targetDate <= dates[0]) return 0;
        if (targetDate >= dates[dates.length - 1]) return dates.length - 1;
        let lo = 0, hi = dates.length - 1;
        while (lo < hi - 1) {
            const mid = Math.floor((lo + hi) / 2);
            if (dates[mid] <= targetDate) lo = mid; else hi = mid;
        }
        const diffLo = Math.abs(new Date(targetDate).getTime() - new Date(dates[lo]).getTime());
        const diffHi = Math.abs(new Date(dates[hi]).getTime() - new Date(targetDate).getTime());
        return diffLo <= diffHi ? lo : hi;
    }

    displayLabel.addEventListener('click', () => {
        if (isLoading) return;
        displayLabel.style.display = 'none';
        dateInput.style.display = '';
        dateInput.focus();
        dateInput.showPicker?.();
    });

    const commitDateInput = () => {
        dateInput.style.display = 'none';
        displayLabel.style.display = '';
        if (dateInput.value) {
            const nearest = findNearestIdx(dateInput.value);
            if (nearest !== idx) navigateTo(nearest);
        }
    };

    dateInput.addEventListener('change', commitDateInput);
    dateInput.addEventListener('blur', commitDateInput);

    async function navigateTo(newIdx: number): Promise<void> {
        if (isLoading) return;
        showingStatic = false;
        isLoading = true;
        idx = newIdx;
        sync();
        const state = dateStrToState(dates[idx]);
        pushStateToURL({ year: state.currentYear, month: state.currentMonth, day: state.currentDay });
        await switchDate(dates[idx]);
        setTimeout(() => { isLoading = false; sync(); }, 300);
    }

    prevBtn.addEventListener('click', () => { if (idx > 0) navigateTo(idx - 1); });
    nextBtn.addEventListener('click', () => { if (idx < dates.length - 1) navigateTo(idx + 1); });

    window.addEventListener('popstate', async () => {
        const state = getStateFromURL();
        const target = stateToDateStr(state);
        const targetIdx = dates.indexOf(target);
        if (targetIdx >= 0 && targetIdx !== idx && !isLoading) {
            isLoading = true;
            idx = targetIdx;
            sync();
            await switchDate(dates[idx]);
            setTimeout(() => { isLoading = false; sync(); }, 300);
        }
    });

    nav.appendChild(prevBtn);
    nav.appendChild(displayLabel);
    nav.appendChild(dateInput);
    nav.appendChild(nextBtn);
    container.appendChild(nav);
    document.getElementById('map')!.appendChild(container);
    sync();
}

// Initialize UI
buildControls();

buildNavigator(generateDatesForCollection(currentCollection));
