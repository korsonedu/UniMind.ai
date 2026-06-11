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

// ── Math ──
mat3 rotY(float a){float s=sin(a),c=cos(a);return mat3(c,0,s,0,1,0,-s,0,c);}
mat3 rotX(float a){float s=sin(a),c=cos(a);return mat3(1,0,0,0,c,-s,0,s,c);}

// ── 9 polyhedron nodes at varying depths ──
// Outer shell (visible at edges) + inner core (visible at center)
vec3 N0=vec3(0.00,1.25,0.00);  vec3 N1=vec3(0.90,0.45,0.40);
vec3 N2=vec3(0.55,0.35,-0.85); vec3 N3=vec3(-0.80,0.50,0.45);
vec3 N4=vec3(-0.45,-0.30,-0.75); vec3 N5=vec3(0.65,-0.40,0.55);
vec3 N6=vec3(0.05,0.02,0.20);    vec3 N7=vec3(-0.12,0.05,0.15);
vec3 N8=vec3(0.02,-0.15,0.25);

// ── Node colors (knowledge-graph palette) ──
vec3 cGreen=vec3(0.133,0.773,0.369);
vec3 cAmber=vec3(0.961,0.619,0.043);
vec3 cRed=vec3(0.937,0.267,0.267);
vec3 cGray=vec3(0.612,0.639,0.686);

vec3 nodeColor(int i){
  if(i==0||i==1||i==6)return cGreen;
  if(i==2||i==5)return cAmber;
  if(i==3||i==4)return cRed;
  return cGray;
}
float nodeRad(int i){
  if(i==0)return 0.12;
  if(i<=5)return 0.09;
  return 0.07; // inner nodes
}

// ── Scene SDF: node spheres only ──
float sceneSDF(vec3 p){
  float d=1e9;
  d=min(d,length(p-N0)-nodeRad(0));
  d=min(d,length(p-N1)-nodeRad(1));
  d=min(d,length(p-N2)-nodeRad(2));
  d=min(d,length(p-N3)-nodeRad(3));
  d=min(d,length(p-N4)-nodeRad(4));
  d=min(d,length(p-N5)-nodeRad(5));
  d=min(d,length(p-N6)-nodeRad(6));
  d=min(d,length(p-N7)-nodeRad(7));
  d=min(d,length(p-N8)-nodeRad(8));
  return d;
}

vec3 normal(vec3 p){
  const vec2 e=vec2(0.003,0);
  return normalize(vec3(sceneSDF(p+e.xyy)-sceneSDF(p-e.xyy),
                        sceneSDF(p+e.yxy)-sceneSDF(p-e.yxy),
                        sceneSDF(p+e.yyx)-sceneSDF(p-e.yyx)));
}

// ── 3D → screen projection ──
vec3 proj(vec3 p,vec3 ro,vec3 fwd,vec3 ri,vec3 up,float asp){
  vec3 d=p-ro;
  float z=dot(d,fwd);
  if(z<0.05)return vec3(0,0,-1);
  return vec3(dot(d,ri)/z/asp, dot(d,up)/z, z);
}

// ── Edge helper: draw line + electric pulse ──
void edge(inout vec3 col,vec3 sa,vec3 sb,int a,int b){
  if(sa.z<0.05||sb.z<0.05)return;
  vec2 uv=v*2.0-1.0;
  vec2 A=vec2(sa.x,sa.y),B=vec2(sb.x,sb.y);
  vec2 ab=B-A;
  float len=length(ab);
  if(len<0.001)return;
  float h=clamp(dot(uv-A,ab)/(len*len),0.0,1.0);
  float dist=length(uv-(A+ab*h));
  float avgZ=(sa.z+sb.z)*0.5;

  // Static wire: thin + glow
  float th=0.002/avgZ;
  float lw=smoothstep(th,th*0.3,dist);
  float mask=smoothstep(0.03,0.08,h)*smoothstep(0.03,0.08,1.0-h);
  col=mix(col,vec3(0.4,0.45,0.55),lw*mask*0.6);
  col=mix(col,vec3(0.6,0.65,0.8),smoothstep(th*3.0,th,dist)*mask*0.15);

  // Electric pulse — bright spark traveling along edge
  vec3 pc=mix(nodeColor(a),nodeColor(b),0.5);
  float spd=0.3+float(a+b)*0.02;
  float ph=fract(t*spd+float(a)*0.1);
  float pd=abs(h-ph)/avgZ;
  float spark=smoothstep(0.015,0.002,pd);
  spark+=smoothstep(0.04,0.01,pd)*0.4;
  float emask=smoothstep(0.04,0.12,h)*smoothstep(0.04,0.12,1.0-h);
  col=mix(col,pc*2.0,spark*emask);
  col=mix(col,vec3(1.0),spark*emask*0.5);

  // Second pulse (opposite direction)
  float ph2=fract(t*spd*1.3+0.5+float(b)*0.07);
  float pd2=abs(h-ph2)/avgZ;
  float spark2=smoothstep(0.015,0.002,pd2);
  spark2+=smoothstep(0.04,0.01,pd2)*0.4;
  col=mix(col,pc*2.0,spark2*emask);
  col=mix(col,vec3(1.0),spark2*emask*0.5);
}

void main(){
  float asp=r.x/r.y;
  vec2 uv=v*2.0-1.0;

  // Camera
  float ca=t*0.12;
  vec3 ro=vec3(sin(ca)*2.5,sin(t*0.08)*0.2,cos(ca)*2.5);
  vec3 fwd=normalize(-ro);
  vec3 ri=normalize(cross(fwd,vec3(0,1,0)));
  vec3 up=cross(ri,fwd);
  vec3 rd=normalize(fwd+uv.x*ri+uv.y*up);

  // Rotate nodes
  mat3 world=rotY(t*0.18)*rotX(sin(t*0.12)*0.3);
  vec3 R0=world*N0; vec3 R1=world*N1; vec3 R2=world*N2;
  vec3 R3=world*N3; vec3 R4=world*N4; vec3 R5=world*N5;
  vec3 R6=world*N6; vec3 R7=world*N7; vec3 R8=world*N8;

  // ── Background ──
  vec3 col=vec3(0.95,0.95,0.96);

  // ── Raymarch nodes ──
  float d=0.0;
  int hit=-1;
  for(int s=0;s<64;s++){
    float h=1e9;
    h=min(h,length(ro+rd*d-R0)-nodeRad(0));
    h=min(h,length(ro+rd*d-R1)-nodeRad(1));
    h=min(h,length(ro+rd*d-R2)-nodeRad(2));
    h=min(h,length(ro+rd*d-R3)-nodeRad(3));
    h=min(h,length(ro+rd*d-R4)-nodeRad(4));
    h=min(h,length(ro+rd*d-R5)-nodeRad(5));
    h=min(h,length(ro+rd*d-R6)-nodeRad(6));
    h=min(h,length(ro+rd*d-R7)-nodeRad(7));
    h=min(h,length(ro+rd*d-R8)-nodeRad(8));
    if(h<0.002){hit=0;break;}
    d+=h;
    if(d>4.0)break;
  }

  if(hit>=0){
    vec3 p=ro+rd*d;
    vec3 n=normal(p);

    // Identify closest node (no array indexing — GLSL ES 1.0 compat)
    float d0=length(p-R0),d1=length(p-R1),d2=length(p-R2);
    float d3=length(p-R3),d4=length(p-R4),d5=length(p-R5);
    float d6=length(p-R6),d7=length(p-R7),d8=length(p-R8);
    
    vec3 nc; float nr; float dist;
    if(d0<d1&&d0<d2&&d0<d3&&d0<d4&&d0<d5&&d0<d6&&d0<d7&&d0<d8){nc=nodeColor(0);nr=nodeRad(0);dist=d0;}
    else if(d1<d2&&d1<d3&&d1<d4&&d1<d5&&d1<d6&&d1<d7&&d1<d8){nc=nodeColor(1);nr=nodeRad(1);dist=d1;}
    else if(d2<d3&&d2<d4&&d2<d5&&d2<d6&&d2<d7&&d2<d8){nc=nodeColor(2);nr=nodeRad(2);dist=d2;}
    else if(d3<d4&&d3<d5&&d3<d6&&d3<d7&&d3<d8){nc=nodeColor(3);nr=nodeRad(3);dist=d3;}
    else if(d4<d5&&d4<d6&&d4<d7&&d4<d8){nc=nodeColor(4);nr=nodeRad(4);dist=d4;}
    else if(d5<d6&&d5<d7&&d5<d8){nc=nodeColor(5);nr=nodeRad(5);dist=d5;}
    else if(d6<d7&&d6<d8){nc=nodeColor(6);nr=nodeRad(6);dist=d6;}
    else if(d7<d8){nc=nodeColor(7);nr=nodeRad(7);dist=d7;}
    else{nc=nodeColor(8);nr=nodeRad(8);dist=d8;}

    // Core: bright center
    float core=smoothstep(nr,nr*0.3,dist);

    // Rim lighting
    float rim=pow(1.0-max(dot(-rd,n),0.0),3.0);

    // Diffuse
    float diff=max(dot(n,normalize(vec3(0.5,0.8,0.4))),0.0);

    col=nc*(0.25+diff*0.45);
    col=mix(nc*2.0,col,core);            // bright core
    col+=nc*rim*0.5;                     // rim glow
    col+=vec3(0.9)*core*0.3;             // white hotspot
  }

  // ── Project all nodes ──
  vec3 s0=proj(R0,ro,fwd,ri,up,asp); vec3 s1=proj(R1,ro,fwd,ri,up,asp);
  vec3 s2=proj(R2,ro,fwd,ri,up,asp); vec3 s3=proj(R3,ro,fwd,ri,up,asp);
  vec3 s4=proj(R4,ro,fwd,ri,up,asp); vec3 s5=proj(R5,ro,fwd,ri,up,asp);
  vec3 s6=proj(R6,ro,fwd,ri,up,asp); vec3 s7=proj(R7,ro,fwd,ri,up,asp);
  vec3 s8=proj(R8,ro,fwd,ri,up,asp);

  // ── Draw all edges with electric pulses ──
  edge(col,s0,s1,0,1); edge(col,s0,s3,0,3); edge(col,s0,s4,0,4);
  edge(col,s0,s5,0,5); edge(col,s1,s2,1,2); edge(col,s1,s5,1,5);
  edge(col,s1,s6,1,6); edge(col,s2,s4,2,4); edge(col,s2,s6,2,6);
  edge(col,s3,s5,3,5); edge(col,s3,s7,3,7); edge(col,s4,s8,4,8);
  edge(col,s5,s8,5,8); edge(col,s6,s7,6,7); edge(col,s7,s8,7,8);
  edge(col,s6,s8,6,8); edge(col,s3,s4,3,4); edge(col,s2,s5,2,5);
  edge(col,s1,s7,1,7); edge(col,s0,s7,0,7); edge(col,s4,s6,4,6);
  edge(col,s2,s8,2,8);

  // ── Particle field ──
  for(int i=0;i<16;i++){
    float fi=float(i);
    float ang=fi*0.45+t*(0.08+fi*0.005);
    float rad=1.2+sin(t*0.3+fi)*0.35;
    float yOff=sin(fi*1.3+t*0.35)*0.6;
    vec3 sp=vec3(sin(ang)*rad,yOff,cos(ang)*rad);
    vec3 spp=proj(sp,ro,fwd,ri,up,asp);
    if(spp.z<0.0)continue;
    float pDist=length(uv-vec2(spp.x,spp.y));
    float pSize=0.02/spp.z;
    float pAlpha=smoothstep(pSize,pSize*0.2,pDist);
    int ci=i-(i/9)*9; // GLSL ES 1.0 no int %
    vec3 pCol=mix(nodeColor(ci),vec3(0.7,0.75,0.85),0.4);
    col=mix(col,pCol,pAlpha*0.4);
  }

  // Subtle vignette
  col*=1.0-length(uv)*0.08;

  gl_FragColor=vec4(col,1.0);
}
`;

export const KnowledgeGraphCanvas: React.FC = () => {
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
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1,3,-1,-1,3]), gl.STATIC_DRAW);

    const compile = (type: number, src: string) => {
      const s = gl.createShader(type)!;
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if(!gl.getShaderParameter(s,gl.COMPILE_STATUS)){console.error(gl.getShaderInfoLog(s));return null;}
      return s;
    };

    const vs=compile(gl.VERTEX_SHADER,VERT),fs=compile(gl.FRAGMENT_SHADER,FRAG);
    if(!vs||!fs)return;
    const prog=gl.createProgram()!;
    gl.attachShader(prog,vs);gl.attachShader(prog,fs);gl.linkProgram(prog);
    if(!gl.getProgramParameter(prog,gl.LINK_STATUS)){console.error(gl.getProgramInfoLog(prog));return;}
    gl.useProgram(prog);

    const a=gl.getAttribLocation(prog,'a');
    gl.enableVertexAttribArray(a);
    gl.vertexAttribPointer(a,2,gl.FLOAT,false,0,0);
    const uT=gl.getUniformLocation(prog,'t'),uR=gl.getUniformLocation(prog,'r');

    let pt=0,acc=0;
    const frame=(now:number)=>{
      rafRef.current=requestAnimationFrame(frame);
      const dt=pt?(now-pt)/1000:0;pt=now;acc+=dt;
      gl.uniform1f(uT,acc);
      gl.uniform2f(uR,canvas.width,canvas.height);
      gl.drawArrays(gl.TRIANGLES,0,3);
    };
    rafRef.current=requestAnimationFrame(frame);
    return()=>{cancelAnimationFrame(rafRef.current);window.removeEventListener('resize',resize);};
  },[]);

  return <canvas ref={canvasRef} style={{position:'absolute',top:0,left:0,width:'100%',height:'100%',display:'block'}}/>;
};
