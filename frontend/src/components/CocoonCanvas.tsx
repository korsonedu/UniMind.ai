import React, { useRef, useEffect } from 'react';

const VERT = `
attribute vec2 a;
varying vec2 v;
void main(){v=a*0.5+0.5;gl_Position=vec4(a,0,1);}
`;

const FRAG = `
precision highp float;
varying vec2 v;
uniform float t;
uniform vec2 r;

// Noise
vec4 perm(vec4 x){return mod(((x*34.)+1.)*x,289.);}
float snoise(vec3 v){
  const vec2 C=vec2(1./6.,1./3.);
  const vec4 D=vec4(0.,.5,1.,2.);
  vec3 i=floor(v+dot(v,C.yyy));
  vec3 x0=v-i+dot(i,C.xxx);
  vec3 g=step(x0.yzx,x0.xyz),l=1.-g;
  vec3 i1=min(g.xyz,l.zxy),i2=max(g.xyz,l.zxy);
  vec3 x1=x0-i1+C.xxx,x2=x0-i2+C.yyy,x3=x0-D.yyy;
  i=mod(i,289.);
  vec4 p=perm(perm(perm(i.z+vec4(0.,i1.z,i2.z,1.))+i.y+vec4(0.,i1.y,i2.y,1.))+i.x+vec4(0.,i1.x,i2.x,1.));
  vec3 ns=1./7.*D.wyz-D.xzx;
  vec4 j=p-49.*floor(p*ns.z*ns.z);
  vec4 x_=floor(j*ns.z),y_=floor(j-7.*x_);
  vec4 x=x_*ns.x+ns.yyyy,y=y_*ns.x+ns.yyyy,h=1.-abs(x)-abs(y);
  vec4 b0=vec4(x.xy,y.xy),b1=vec4(x.zw,y.zw);
  vec4 s0=floor(b0)*2.+1.,s1=floor(b1)*2.+1.,sh=-step(h,vec4(0.));
  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy,a1=b1.xzyw+s1.xzyw*sh.zzww;
  vec3 p0=vec3(a0.xy,h.x),p1=vec3(a0.zw,h.y),p2=vec3(a1.xy,h.z),p3=vec3(a1.zw,h.w);
  vec4 nm=1.7928-0.8537*vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3));
  p0*=nm.x;p1*=nm.y;p2*=nm.z;p3*=nm.w;
  vec4 m=max(.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.);
  m=m*m;
  return 42.*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}

// Rough cocoon SDF
float cocoon(vec3 p){
  vec3 q=p; q.y*=1.25;
  float d=length(q)-1.0;
  d+=snoise(p*1.5+t*0.05)*0.15;
  d+=snoise(p*2.5+3.0)*0.10;
  d+=snoise(p*4.5+t*0.03)*0.05;
  return d;
}

// 12 nodes on sphere
const vec3 N0=vec3(0,1,0);
const vec3 N1=normalize(vec3(1,.5,0));
const vec3 N2=normalize(vec3(.3,.5,.9));
const vec3 N3=normalize(vec3(-.8,.5,.4));
const vec3 N4=normalize(vec3(-.6,.4,-.7));
const vec3 N5=normalize(vec3(.4,.3,-.85));
const vec3 N6=normalize(vec3(.7,-.4,.6));
const vec3 N7=normalize(vec3(-.5,-.3,.8));
const vec3 N8=normalize(vec3(-.9,-.3,0));
const vec3 N9=normalize(vec3(-.3,-.5,-.8));
const vec3 N10=normalize(vec3(.6,-.6,-.5));
const vec3 N11=vec3(0,-1,0);

float sceneSDF(vec3 p){
  float d=cocoon(p);
  d=min(d,length(p-N0*1.02)-0.06);
  d=min(d,length(p-N1*1.02)-0.05);
  d=min(d,length(p-N2*1.02)-0.05);
  d=min(d,length(p-N3*1.02)-0.05);
  d=min(d,length(p-N4*1.02)-0.05);
  d=min(d,length(p-N5*1.02)-0.05);
  d=min(d,length(p-N6*1.02)-0.05);
  d=min(d,length(p-N7*1.02)-0.05);
  d=min(d,length(p-N8*1.02)-0.05);
  d=min(d,length(p-N9*1.02)-0.05);
  d=min(d,length(p-N10*1.02)-0.05);
  d=min(d,length(p-N11*1.02)-0.06);
  return d;
}

float raymarch(vec3 ro,vec3 rd){
  float d=0.;
  for(int i=0;i<80;i++){
    float h=sceneSDF(ro+rd*d);
    if(h<.003)break;
    d+=h;
    if(d>5.)break;
  }
  return d;
}

vec3 calcNormal(vec3 p){
  const vec2 e=vec2(.004,0);
  return normalize(vec3(
    sceneSDF(p+e.xyy)-sceneSDF(p-e.xyy),
    sceneSDF(p+e.yxy)-sceneSDF(p-e.yxy),
    sceneSDF(p+e.yyx)-sceneSDF(p-e.yyx)
  ));
}

void main(){
  vec2 uv=(v*2.-1.);
  uv.x*=r.x/r.y;

  float camAngle=t*0.05;
  vec3 ro=vec3(sin(camAngle)*2.7, sin(t*0.1)*0.1, cos(camAngle)*2.7);
  vec3 fwd=normalize(-ro);
  vec3 right=normalize(cross(fwd,vec3(0,1,0)));
  vec3 up=cross(right,fwd);
  vec3 rd=normalize(fwd+uv.x*right+uv.y*up);

  vec3 col=vec3(0.015,0.018,0.04);

  float d=raymarch(ro,rd);
  if(d<5.){
    vec3 p=ro+rd*d;
    vec3 n=calcNormal(p);
    float rim=pow(1.-max(dot(-rd,n),0.),3.0);

    // Neural color
    vec3 c1=vec3(0.2,0.5,1.0);
    vec3 c2=vec3(0.0,0.9,0.75);
    vec3 c3=vec3(0.6,0.2,1.0);
    float cs=sin(t*0.15)*0.5+0.5;
    vec3 neural=mix(c1,c2,cs);
    neural=mix(neural,c3,sin(t*0.22+1.)*0.5+0.5);

    // Is this a node?
    float nd=1e9;
    nd=min(nd,length(p-N0*1.02)-0.06);
    nd=min(nd,length(p-N1*1.02)-0.05);
    nd=min(nd,length(p-N2*1.02)-0.05);
    nd=min(nd,length(p-N3*1.02)-0.05);
    nd=min(nd,length(p-N4*1.02)-0.05);
    nd=min(nd,length(p-N5*1.02)-0.05);
    nd=min(nd,length(p-N6*1.02)-0.05);
    nd=min(nd,length(p-N7*1.02)-0.05);
    nd=min(nd,length(p-N8*1.02)-0.05);
    nd=min(nd,length(p-N9*1.02)-0.05);
    nd=min(nd,length(p-N10*1.02)-0.05);
    nd=min(nd,length(p-N11*1.02)-0.06);

    if(nd<0.0){
      // Node: bright white-blue core
      float pulse=sin(t*2.5)*0.3+0.7;
      float glow=smoothstep(0.0,-0.04,nd);
      col=vec3(0.9,0.95,1.0)*glow*pulse;
      col+=neural*glow*0.6;
    } else {
      // Rough surface
      float diff=max(dot(n,normalize(vec3(0.4,0.8,0.3))),0.0);
      diff=pow(diff,0.5);
      // BRIGHT surface — not too dark
      col=vec3(0.07,0.09,0.16)*(0.35+diff*0.65);
      col+=neural*rim*0.15;
      // Surface noise detail
      float nd2=snoise(p*8.0)*0.5+0.5;
      col+=neural*0.03*nd2;
    }
  }

  // ── Synapse flowing light (2D overlay) ──
  #define SG(va,vb,spd,phs) { \
    vec3 A=va*1.02, B=vb*1.02; \
    vec3 ab=B-A; \
    vec3 w=ro-A; \
    float h=clamp(-dot(w,ab)/dot(ab,ab),0.0,1.0); \
    vec3 cp=A+ab*h; \
    float dist=length(ro+rd*dot(cp-ro,rd)-cp); \
    float lineCore=smoothstep(0.008,0.001,dist); \
    float lineGlow=smoothstep(0.03,0.005,dist); \
    col+=vec3(0.08,0.18,0.35)*lineGlow; \
    col+=vec3(0.15,0.35,0.65)*lineCore; \
    float pulse=smoothstep(0.15,0.0,abs(h-fract(t*spd+phs))); \
    pulse+=smoothstep(0.15,0.0,abs(h-fract(t*spd+phs+0.5))); \
    col+=vec3(0.4,0.7,1.0)*smoothstep(0.03,0.003,dist)*pulse; \
    col+=vec3(0.8,0.95,1.0)*smoothstep(0.01,0.0,dist)*pulse*2.0; \
  }

  // Neural color for synapses
  vec3 nc1=vec3(0.2,0.5,1.0);
  vec3 nc2=vec3(0.0,0.9,0.75);
  vec3 nc3=vec3(0.6,0.2,1.0);
  float ncs=sin(t*0.15)*0.5+0.5;
  vec3 nmix=mix(nc1,nc2,ncs);
  nmix=mix(nmix,nc3,sin(t*0.22+1.)*0.5+0.5);

  SG(N0,N1,0.22,0.0) SG(N0,N2,0.28,0.3) SG(N0,N3,0.18,0.6)
  SG(N1,N5,0.32,0.1) SG(N2,N6,0.25,0.5) SG(N3,N7,0.2,0.8)
  SG(N4,N8,0.3,0.2)  SG(N5,N10,0.16,0.7) SG(N6,N7,0.24,0.4)
  SG(N9,N11,0.28,0.9) SG(N10,N11,0.22,0.15) SG(N7,N8,0.26,0.55)
  SG(N1,N2,0.19,0.35) SG(N4,N5,0.23,0.75) SG(N8,N9,0.27,0.45) SG(N9,N10,0.21,0.65)
  #undef SG

  // Particles
  for(int i=0;i<20;i++){
    float fi=float(i);
    float ang=fi*2.39996+t*(0.1+fi*0.006);
    float rad=1.4+sin(t*0.4+fi)*0.3;
    float yO=sin(fi*1.5+t*0.35)*0.5;
    vec3 sp=vec3(sin(ang)*rad,yO,cos(ang)*rad)-ro;
    float pj=dot(sp,rd);
    vec3 cl=ro+rd*max(pj,0.);
    float dist=length(cl-(sp+ro));
    col+=mix(vec3(0.2,0.5,1.0),vec3(0.5,0.2,1.0),fi/20.)*smoothstep(.025,.0,dist)*0.4;
  }

  col*=1.-length(uv)*0.15;
  gl_FragColor=vec4(clamp(col,0.,1.),1.);
}
`;

export const CocoonCanvas: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = canvas.getContext('webgl', { antialias: true, alpha: false });
    if (!gl) return;

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
      gl.viewport(0, 0, canvas.width, canvas.height);
    };
    resize();
    window.addEventListener('resize', resize);

    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);

    const compile = (type: number, src: string) => {
      const s = gl.createShader(type)!;
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) { console.error(gl.getShaderInfoLog(s)); return null; }
      return s;
    };

    const prog = gl.createProgram()!;
    const vs = compile(gl.VERTEX_SHADER, VERT);
    const fs = compile(gl.FRAGMENT_SHADER, FRAG);
    if (!vs || !fs) return;
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    gl.useProgram(prog);

    const aPos = gl.getAttribLocation(prog, 'a');
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);
    const uT = gl.getUniformLocation(prog, 't');
    const uR = gl.getUniformLocation(prog, 'r');

    let pt = 0, acc = 0;
    const frame = (now: number) => {
      rafRef.current = requestAnimationFrame(frame);
      const dt = pt ? (now - pt) / 1000 : 0;
      pt = now; acc += dt;
      gl.uniform1f(uT, acc);
      gl.uniform2f(uR, canvas.width, canvas.height);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    };
    rafRef.current = requestAnimationFrame(frame);

    return () => { cancelAnimationFrame(rafRef.current); window.removeEventListener('resize', resize); };
  }, []);

  return <canvas ref={canvasRef} style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', display: 'block' }} />;
};
