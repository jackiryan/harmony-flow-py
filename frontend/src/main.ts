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

// 1. Load the PNG
interface CurrentData {
    data: Uint8ClampedArray;
    width: number;
    height: number;
}

const currentData: Promise<CurrentData> = new Promise((resolve, reject) => {
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
            height: image.height
        });
    };
    image.onerror = () => reject(new Error('failed to load'));
    image.src = '/oscar_test.png'; 
});

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

const minU = -2.92, maxU = 2.93, deltaU = maxU - minU;
const minV = -2.81, maxV = 2.69, deltaV = maxV - minV;

// 4. Data Loader
const currents = new DataTileSource({
    projection: 'EPSG:4326',
    tileGrid: dataTileGrid,
    transition: 0,
    wrapX: true, 
    async loader(z: number, x: number, y: number): Promise<Float32Array> {
        const { data: inputData, width: inputWidth, height: inputHeight } = await currentData;
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

                const xPos = lon360 / degreesPerPixelX;
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
const map = new Map({
    target: 'map',
    layers: [
        new TileLayer({ source: new OSM() }),
    ],
    view: new View({ 
        center: [0, 0], 
        zoom: 2,
        projection: 'EPSG:4326' 
    }),
});

let flowLayer = makeFlowLayer();
map.addLayer(flowLayer);

// 7. Handle Flow Layer Visibility During Drag
let warmUpId: number | null = null;

map.on('movestart', () => {
    if (warmUpId !== null) {
        cancelAnimationFrame(warmUpId);
        warmUpId = null;
    }
    flowLayer.setOpacity(0);
});

map.on('moveend', () => {
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