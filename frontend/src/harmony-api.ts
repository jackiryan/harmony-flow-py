/**
 * Harmony API Client for dynamic PNG texture generation
 */

export interface HarmonyJobResponse {
    jobID: string;
    status: 'running' | 'successful' | 'failed' | 'canceled';
    message?: string;
    progress?: number;
    links?: Array<{ href: string; rel: string; type?: string }>;
    errors?: string[];
}

export interface CollectionConfig {
    id: string;
    name: string;
    shortname: string;
    startDate: string;       // YYYY-MM-DD
    endDate: string | null;  // YYYY-MM-DD or null for 'present'
}

export const OSCAR_COLLECTIONS: Record<string, CollectionConfig> = {
    nrt: {
        id: 'C1241042623-POCLOUD',
        name: 'OSCAR NRT',
        shortname: 'oscar_currents_nrt',
        startDate: '2020-01-01',
        endDate: '2020-12-31'
    },
    final: {
        id: 'C1241367941-POCLOUD',
        name: 'OSCAR FINAL',
        shortname: 'oscar_currents_final',
        startDate: '1993-01-01',
        endDate: '1993-12-31'
    },
    interim: {
        id: 'C1241042622-POCLOUD',
        name: 'OSCAR INTERIM',
        shortname: 'oscar_currents_interim',
        startDate: '2019-01-01',
        endDate: '2019-12-31'
    }
};

export interface VariableConfig {
    name: string;
    variables: [string, string];
}

export const VARIABLE_TYPES: Record<string, VariableConfig> = {
    'u_v': { name: 'Surface Currents (u/v)', variables: ['u', 'v'] },
    'ug_vg': { name: 'Geostrophic Currents (ug/vg)', variables: ['ug', 'vg'] }
};

export function isDateInRange(dateStr: string, collection: CollectionConfig): boolean {
    if (dateStr < collection.startDate) return false;
    if (collection.endDate && dateStr > collection.endDate) return false;
    return true;
}

export class HarmonyClient {
    private baseUrl: string;
    private bearerToken: string | null = null;

    constructor(venue: 'sit' | 'uat' | 'prod' = 'uat') {
        if (venue === 'sit') {
            this.baseUrl = 'https://harmony.sit.earthdata.nasa.gov';
        } else if (venue === 'prod') {
            this.baseUrl = 'https://harmony.earthdata.nasa.gov';
        } else {
            this.baseUrl = 'https://harmony.uat.earthdata.nasa.gov';
        }
    }

    setToken(token: string): void {
        this.bearerToken = token.trim();
    }

    hasToken(): boolean {
        return this.bearerToken !== null && this.bearerToken.length > 0;
    }

    getToken(): string | null {
        return this.bearerToken;
    }

    private buildHeaders(): HeadersInit {
        const headers: Record<string, string> = { 'Accept': 'application/json' };
        if (this.bearerToken) {
            headers['Authorization'] = `Bearer ${this.bearerToken}`;
        }
        return headers;
    }

    /**
     * Submit a request to Harmony to generate a PNG texture.
     * Constructs the granuleName from the collection shortname and date,
     * then submits via the OGC Coverages API.
     */
    async submitRequest(
        collectionId: string,
        shortname: string,
        dateStr: string,          // YYYY-MM-DD
        variables: [string, string]
    ): Promise<string> {
        // Construct granuleName from shortname + date: e.g. oscar_currents_nrt_20200602
        const dateCompact = dateStr.replace(/-/g, '');
        const granuleName = `${shortname}_${dateCompact}`;

        // Build the Harmony OGC Coverages request
        const url = new URL(
            `${this.baseUrl}/${collectionId}/ogc-api-coverages/1.0.0/collections/parameter_vars/coverage/rangeset`,
            window.location.origin
        );

        url.searchParams.set('forceAsync', 'true');
        url.searchParams.set('granuleName', granuleName);
        url.searchParams.set('format', 'image/png');
        variables.forEach(v => url.searchParams.append('variable', v));

        console.log('=== SUBMITTING HARMONY REQUEST ===');
        console.log('Full URL:', url.toString());
        console.log('Collection:', collectionId);
        console.log('Date:', dateStr);
        console.log('Variables:', variables);
        console.log('Headers:', this.buildHeaders());
        console.log('====================================');

        let response;
        try {
            response = await fetch(url.toString(), {
                method: 'GET',
                headers: this.buildHeaders(),
                // Bearer token is sent via Authorization header
            });
        } catch (networkError) {
            console.error('=== NETWORK ERROR ===');
            console.error('Failed to connect to Harmony API');
            console.error('Error:', networkError);
            console.error('URL attempted:', url.toString());
            console.error('=====================');
            const errorMsg = networkError instanceof Error ? networkError.message : String(networkError);
            if (errorMsg.includes('Failed to fetch')) {
                throw new Error(
                    'Authentication failed — Harmony redirected to OAuth login. ' +
                    'Please check that your bearer token is valid. ' +
                    'Generate one at https://uat.urs.earthdata.nasa.gov (Profile \u2192 User Tokens)'
                );
            }
            throw new Error(`Network error: ${errorMsg}`);
        }

        console.log('=== HARMONY API RESPONSE ===');
        console.log('Status:', response.status, response.statusText);
        console.log('Headers:', Object.fromEntries(response.headers.entries()));
        console.log('URL:', response.url);

        if (!response.ok) {
            console.error('=== REQUEST FAILED ===');
            console.error('Status:', response.status, response.statusText);
            console.error('URL:', response.url);
            
            const body = await response.text().catch(() => '(no body)');
            console.error('Response body:', body);
            
            // Try to parse as JSON for better error details
            try {
                const errorJson = JSON.parse(body);
                console.error('Parsed error:', JSON.stringify(errorJson, null, 2));
            } catch {
                console.error('Raw error text:', body);
            }
            
            console.error('======================');
            throw new Error(`Harmony request failed: ${response.status} ${response.statusText} — ${body}`);
        }

        const data: HarmonyJobResponse = await response.json();
        console.log('Response body:', JSON.stringify(data, null, 2));
        console.log('Job ID:', data.jobID);
        console.log('Status:', data.status);
        console.log('Progress:', data.progress);
        console.log('Message:', data.message);
        console.log('========================');
        return data.jobID;
    }

    /**
     * Poll a Harmony job until it completes
     */
    async pollJob(jobId: string, onProgress?: (progress: number, message: string) => void): Promise<{ pngUrl: string; worldFileUrl?: string }> {
        const statusUrl = `${this.baseUrl}/jobs/${jobId}`;
        
        while (true) {
            await new Promise(resolve => setTimeout(resolve, 1000)); // Poll every 1 second

            const response = await fetch(statusUrl, {
                headers: this.buildHeaders()
            });

            if (!response.ok) {
                const body = await response.text().catch(() => '(no body)');
                console.error('Harmony poll error body:', body);
                throw new Error(`Job status check failed: ${response.status} — ${body}`);
            }

            const job: HarmonyJobResponse = await response.json();
            console.log(`[Job ${jobId}] status=${job.status} | progress=${job.progress ?? 0}% | ${job.message ?? ''}`);

            if (onProgress && job.progress !== undefined) {
                onProgress(job.progress, job.message ?? '');
            }

            if (job.status === 'successful') {
                const pngLink = job.links?.find(link => 
                    link.rel === 'data' && 
                    (link.type === 'image/png' || link.href.endsWith('.png'))
                );
                const pgwLink = job.links?.find(link =>
                    link.rel === 'data' &&
                    (link.href.endsWith('.pgw') || link.href.endsWith('.wld'))
                );
                
                if (!pngLink) {
                    throw new Error('No PNG output found in job results');
                }
                
                return { pngUrl: pngLink.href, worldFileUrl: pgwLink?.href };
            } else if (job.status === 'failed' || job.status === 'canceled') {
                console.error('=== JOB FAILED ===');
                console.error('Job ID:', jobId);
                console.error('Status:', job.status);
                console.error('Message:', job.message);
                console.error('Progress:', job.progress);
                console.error('Full job object:', JSON.stringify(job, null, 2));
                
                if (job.errors && job.errors.length > 0) {
                    console.error('Errors:');
                    job.errors.forEach((err, i) => {
                        console.error(`  [${i}] ${err}`);
                    });
                }
                
                console.error('==================');
                throw new Error(`Job ${job.status}: ${job.message || 'Unknown error'}`);
            }
            // Continue polling if status is 'running'
        }
    }

    /**
     * Submit request and wait for completion
     */
    async generateTexture(
        collectionId: string,
        shortname: string,
        dateStr: string,          // YYYY-MM-DD
        variables: [string, string],
        onProgress?: (progress: number, message: string) => void
    ): Promise<{ pngUrl: string; lon0: number }> {
        if (onProgress) {
            onProgress(0, 'Submitting request...');
        }

        const jobId = await this.submitRequest(collectionId, shortname, dateStr, variables);
        
        if (onProgress) {
            onProgress(10, `Job submitted: ${jobId}`);
        }

        const { pngUrl, worldFileUrl } = await this.pollJob(jobId, (progress, message) => {
            if (onProgress) {
                onProgress(10 + (progress * 0.9), message || `Processing... ${Math.round(progress)}%`);
            }
        });
        console.log('PNG URL:', pngUrl);

        let lon0 = 0;
        if (worldFileUrl) {
            try {
                const wfResponse = await fetch(worldFileUrl, { headers: this.buildHeaders() });
                if (wfResponse.ok) {
                    const lines = (await wfResponse.text()).trim().split(/\r?\n/).map(Number);
                    // World file line order: pixel_width, D, B, pixel_height, x_center, y_center
                    // x_center (line 5, index 4) is the center longitude of pixel 0
                    if (lines.length >= 5 && isFinite(lines[4])) {
                        lon0 = lines[4];
                        console.log('World file lon0 (pixel-0 center):', lon0);
                    }
                }
            } catch (e) {
                console.warn('Could not fetch world file, defaulting lon0=0', e);
            }
        }

        return { pngUrl, lon0 };
    }
}
