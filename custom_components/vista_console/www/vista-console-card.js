var At=Object.defineProperty;var xt=Object.getOwnPropertyDescriptor;var g=(i,t,e,s)=>{for(var r=s>1?void 0:s?xt(t,e):t,n=i.length-1,o;n>=0;n--)(o=i[n])&&(r=(s?o(t,e,r):o(r))||r);return s&&r&&At(t,e,r),r};var N=globalThis,I=N.ShadowRoot&&(N.ShadyCSS===void 0||N.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,K=Symbol(),rt=new WeakMap,P=class{constructor(t,e,s){if(this._$cssResult$=!0,s!==K)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=t,this.t=e}get styleSheet(){let t=this.o,e=this.t;if(I&&t===void 0){let s=e!==void 0&&e.length===1;s&&(t=rt.get(e)),t===void 0&&((this.o=t=new CSSStyleSheet).replaceSync(this.cssText),s&&rt.set(e,t))}return t}toString(){return this.cssText}},it=i=>new P(typeof i=="string"?i:i+"",void 0,K),W=(i,...t)=>{let e=i.length===1?i[0]:t.reduce((s,r,n)=>s+(o=>{if(o._$cssResult$===!0)return o.cssText;if(typeof o=="number")return o;throw Error("Value passed to 'css' function must be a 'css' function result: "+o+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(r)+i[n+1],i[0]);return new P(e,i,K)},nt=(i,t)=>{if(I)i.adoptedStyleSheets=t.map(e=>e instanceof CSSStyleSheet?e:e.styleSheet);else for(let e of t){let s=document.createElement("style"),r=N.litNonce;r!==void 0&&s.setAttribute("nonce",r),s.textContent=e.cssText,i.appendChild(s)}},V=I?i=>i:i=>i instanceof CSSStyleSheet?(t=>{let e="";for(let s of t.cssRules)e+=s.cssText;return it(e)})(i):i;var{is:wt,defineProperty:Et,getOwnPropertyDescriptor:St,getOwnPropertyNames:Ct,getOwnPropertySymbols:Pt,getPrototypeOf:kt}=Object,L=globalThis,ot=L.trustedTypes,Ut=ot?ot.emptyScript:"",Ht=L.reactiveElementPolyfillSupport,k=(i,t)=>i,U={toAttribute(i,t){switch(t){case Boolean:i=i?Ut:null;break;case Object:case Array:i=i==null?i:JSON.stringify(i)}return i},fromAttribute(i,t){let e=i;switch(t){case Boolean:e=i!==null;break;case Number:e=i===null?null:Number(i);break;case Object:case Array:try{e=JSON.parse(i)}catch{e=null}}return e}},j=(i,t)=>!wt(i,t),at={attribute:!0,type:String,converter:U,reflect:!1,useDefault:!1,hasChanged:j};Symbol.metadata??=Symbol("metadata"),L.litPropertyMetadata??=new WeakMap;var _=class extends HTMLElement{static addInitializer(t){this._$Ei(),(this.l??=[]).push(t)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(t,e=at){if(e.state&&(e.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(t)&&((e=Object.create(e)).wrapped=!0),this.elementProperties.set(t,e),!e.noAccessor){let s=Symbol(),r=this.getPropertyDescriptor(t,s,e);r!==void 0&&Et(this.prototype,t,r)}}static getPropertyDescriptor(t,e,s){let{get:r,set:n}=St(this.prototype,t)??{get(){return this[e]},set(o){this[e]=o}};return{get:r,set(o){let l=r?.call(this);n?.call(this,o),this.requestUpdate(t,l,s)},configurable:!0,enumerable:!0}}static getPropertyOptions(t){return this.elementProperties.get(t)??at}static _$Ei(){if(this.hasOwnProperty(k("elementProperties")))return;let t=kt(this);t.finalize(),t.l!==void 0&&(this.l=[...t.l]),this.elementProperties=new Map(t.elementProperties)}static finalize(){if(this.hasOwnProperty(k("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(k("properties"))){let e=this.properties,s=[...Ct(e),...Pt(e)];for(let r of s)this.createProperty(r,e[r])}let t=this[Symbol.metadata];if(t!==null){let e=litPropertyMetadata.get(t);if(e!==void 0)for(let[s,r]of e)this.elementProperties.set(s,r)}this._$Eh=new Map;for(let[e,s]of this.elementProperties){let r=this._$Eu(e,s);r!==void 0&&this._$Eh.set(r,e)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(t){let e=[];if(Array.isArray(t)){let s=new Set(t.flat(1/0).reverse());for(let r of s)e.unshift(V(r))}else t!==void 0&&e.push(V(t));return e}static _$Eu(t,e){let s=e.attribute;return s===!1?void 0:typeof s=="string"?s:typeof t=="string"?t.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(t=>this.enableUpdating=t),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(t=>t(this))}addController(t){(this._$EO??=new Set).add(t),this.renderRoot!==void 0&&this.isConnected&&t.hostConnected?.()}removeController(t){this._$EO?.delete(t)}_$E_(){let t=new Map,e=this.constructor.elementProperties;for(let s of e.keys())this.hasOwnProperty(s)&&(t.set(s,this[s]),delete this[s]);t.size>0&&(this._$Ep=t)}createRenderRoot(){let t=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return nt(t,this.constructor.elementStyles),t}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(t=>t.hostConnected?.())}enableUpdating(t){}disconnectedCallback(){this._$EO?.forEach(t=>t.hostDisconnected?.())}attributeChangedCallback(t,e,s){this._$AK(t,s)}_$ET(t,e){let s=this.constructor.elementProperties.get(t),r=this.constructor._$Eu(t,s);if(r!==void 0&&s.reflect===!0){let n=(s.converter?.toAttribute!==void 0?s.converter:U).toAttribute(e,s.type);this._$Em=t,n==null?this.removeAttribute(r):this.setAttribute(r,n),this._$Em=null}}_$AK(t,e){let s=this.constructor,r=s._$Eh.get(t);if(r!==void 0&&this._$Em!==r){let n=s.getPropertyOptions(r),o=typeof n.converter=="function"?{fromAttribute:n.converter}:n.converter?.fromAttribute!==void 0?n.converter:U;this._$Em=r;let l=o.fromAttribute(e,n.type);this[r]=l??this._$Ej?.get(r)??l,this._$Em=null}}requestUpdate(t,e,s,r=!1,n){if(t!==void 0){let o=this.constructor;if(r===!1&&(n=this[t]),s??=o.getPropertyOptions(t),!((s.hasChanged??j)(n,e)||s.useDefault&&s.reflect&&n===this._$Ej?.get(t)&&!this.hasAttribute(o._$Eu(t,s))))return;this.C(t,e,s)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(t,e,{useDefault:s,reflect:r,wrapped:n},o){s&&!(this._$Ej??=new Map).has(t)&&(this._$Ej.set(t,o??e??this[t]),n!==!0||o!==void 0)||(this._$AL.has(t)||(this.hasUpdated||s||(e=void 0),this._$AL.set(t,e)),r===!0&&this._$Em!==t&&(this._$Eq??=new Set).add(t))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(e){Promise.reject(e)}let t=this.scheduleUpdate();return t!=null&&await t,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[r,n]of this._$Ep)this[r]=n;this._$Ep=void 0}let s=this.constructor.elementProperties;if(s.size>0)for(let[r,n]of s){let{wrapped:o}=n,l=this[r];o!==!0||this._$AL.has(r)||l===void 0||this.C(r,void 0,n,l)}}let t=!1,e=this._$AL;try{t=this.shouldUpdate(e),t?(this.willUpdate(e),this._$EO?.forEach(s=>s.hostUpdate?.()),this.update(e)):this._$EM()}catch(s){throw t=!1,this._$EM(),s}t&&this._$AE(e)}willUpdate(t){}_$AE(t){this._$EO?.forEach(e=>e.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(t)),this.updated(t)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(t){return!0}update(t){this._$Eq&&=this._$Eq.forEach(e=>this._$ET(e,this[e])),this._$EM()}updated(t){}firstUpdated(t){}};_.elementStyles=[],_.shadowRootOptions={mode:"open"},_[k("elementProperties")]=new Map,_[k("finalized")]=new Map,Ht?.({ReactiveElement:_}),(L.reactiveElementVersions??=[]).push("2.1.2");var X=globalThis,lt=i=>i,D=X.trustedTypes,ct=D?D.createPolicy("lit-html",{createHTML:i=>i}):void 0,gt="$lit$",b=`lit$${Math.random().toFixed(9).slice(2)}$`,ft="?"+b,Rt=`<${ft}>`,w=document,R=()=>w.createComment(""),T=i=>i===null||typeof i!="object"&&typeof i!="function",tt=Array.isArray,Tt=i=>tt(i)||typeof i?.[Symbol.iterator]=="function",F=`[ 	
\f\r]`,H=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,dt=/-->/g,ht=/>/g,A=RegExp(`>|${F}(?:([^\\s"'>=/]+)(${F}*=${F}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),pt=/'/g,ut=/"/g,_t=/^(?:script|style|textarea|title)$/i,et=i=>(t,...e)=>({_$litType$:i,strings:t,values:e}),u=et(1),Kt=et(2),Wt=et(3),E=Symbol.for("lit-noChange"),d=Symbol.for("lit-nothing"),mt=new WeakMap,x=w.createTreeWalker(w,129);function vt(i,t){if(!tt(i)||!i.hasOwnProperty("raw"))throw Error("invalid template strings array");return ct!==void 0?ct.createHTML(t):t}var Mt=(i,t)=>{let e=i.length-1,s=[],r,n=t===2?"<svg>":t===3?"<math>":"",o=H;for(let l=0;l<e;l++){let a=i[l],h,p,c=-1,f=0;for(;f<a.length&&(o.lastIndex=f,p=o.exec(a),p!==null);)f=o.lastIndex,o===H?p[1]==="!--"?o=dt:p[1]!==void 0?o=ht:p[2]!==void 0?(_t.test(p[2])&&(r=RegExp("</"+p[2],"g")),o=A):p[3]!==void 0&&(o=A):o===A?p[0]===">"?(o=r??H,c=-1):p[1]===void 0?c=-2:(c=o.lastIndex-p[2].length,h=p[1],o=p[3]===void 0?A:p[3]==='"'?ut:pt):o===ut||o===pt?o=A:o===dt||o===ht?o=H:(o=A,r=void 0);let y=o===A&&i[l+1].startsWith("/>")?" ":"";n+=o===H?a+Rt:c>=0?(s.push(h),a.slice(0,c)+gt+a.slice(c)+b+y):a+b+(c===-2?l:y)}return[vt(i,n+(i[e]||"<?>")+(t===2?"</svg>":t===3?"</math>":"")),s]},M=class i{constructor({strings:t,_$litType$:e},s){let r;this.parts=[];let n=0,o=0,l=t.length-1,a=this.parts,[h,p]=Mt(t,e);if(this.el=i.createElement(h,s),x.currentNode=this.el.content,e===2||e===3){let c=this.el.content.firstChild;c.replaceWith(...c.childNodes)}for(;(r=x.nextNode())!==null&&a.length<l;){if(r.nodeType===1){if(r.hasAttributes())for(let c of r.getAttributeNames())if(c.endsWith(gt)){let f=p[o++],y=r.getAttribute(c).split(b),z=/([.?@])?(.*)/.exec(f);a.push({type:1,index:n,name:z[2],strings:y,ctor:z[1]==="."?J:z[1]==="?"?Y:z[1]==="@"?G:C}),r.removeAttribute(c)}else c.startsWith(b)&&(a.push({type:6,index:n}),r.removeAttribute(c));if(_t.test(r.tagName)){let c=r.textContent.split(b),f=c.length-1;if(f>0){r.textContent=D?D.emptyScript:"";for(let y=0;y<f;y++)r.append(c[y],R()),x.nextNode(),a.push({type:2,index:++n});r.append(c[f],R())}}}else if(r.nodeType===8)if(r.data===ft)a.push({type:2,index:n});else{let c=-1;for(;(c=r.data.indexOf(b,c+1))!==-1;)a.push({type:7,index:n}),c+=b.length-1}n++}}static createElement(t,e){let s=w.createElement("template");return s.innerHTML=t,s}};function S(i,t,e=i,s){if(t===E)return t;let r=s!==void 0?e._$Co?.[s]:e._$Cl,n=T(t)?void 0:t._$litDirective$;return r?.constructor!==n&&(r?._$AO?.(!1),n===void 0?r=void 0:(r=new n(i),r._$AT(i,e,s)),s!==void 0?(e._$Co??=[])[s]=r:e._$Cl=r),r!==void 0&&(t=S(i,r._$AS(i,t.values),r,s)),t}var Z=class{constructor(t,e){this._$AV=[],this._$AN=void 0,this._$AD=t,this._$AM=e}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(t){let{el:{content:e},parts:s}=this._$AD,r=(t?.creationScope??w).importNode(e,!0);x.currentNode=r;let n=x.nextNode(),o=0,l=0,a=s[0];for(;a!==void 0;){if(o===a.index){let h;a.type===2?h=new O(n,n.nextSibling,this,t):a.type===1?h=new a.ctor(n,a.name,a.strings,this,t):a.type===6&&(h=new Q(n,this,t)),this._$AV.push(h),a=s[++l]}o!==a?.index&&(n=x.nextNode(),o++)}return x.currentNode=w,r}p(t){let e=0;for(let s of this._$AV)s!==void 0&&(s.strings!==void 0?(s._$AI(t,s,e),e+=s.strings.length-2):s._$AI(t[e])),e++}},O=class i{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(t,e,s,r){this.type=2,this._$AH=d,this._$AN=void 0,this._$AA=t,this._$AB=e,this._$AM=s,this.options=r,this._$Cv=r?.isConnected??!0}get parentNode(){let t=this._$AA.parentNode,e=this._$AM;return e!==void 0&&t?.nodeType===11&&(t=e.parentNode),t}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(t,e=this){t=S(this,t,e),T(t)?t===d||t==null||t===""?(this._$AH!==d&&this._$AR(),this._$AH=d):t!==this._$AH&&t!==E&&this._(t):t._$litType$!==void 0?this.$(t):t.nodeType!==void 0?this.T(t):Tt(t)?this.k(t):this._(t)}O(t){return this._$AA.parentNode.insertBefore(t,this._$AB)}T(t){this._$AH!==t&&(this._$AR(),this._$AH=this.O(t))}_(t){this._$AH!==d&&T(this._$AH)?this._$AA.nextSibling.data=t:this.T(w.createTextNode(t)),this._$AH=t}$(t){let{values:e,_$litType$:s}=t,r=typeof s=="number"?this._$AC(t):(s.el===void 0&&(s.el=M.createElement(vt(s.h,s.h[0]),this.options)),s);if(this._$AH?._$AD===r)this._$AH.p(e);else{let n=new Z(r,this),o=n.u(this.options);n.p(e),this.T(o),this._$AH=n}}_$AC(t){let e=mt.get(t.strings);return e===void 0&&mt.set(t.strings,e=new M(t)),e}k(t){tt(this._$AH)||(this._$AH=[],this._$AR());let e=this._$AH,s,r=0;for(let n of t)r===e.length?e.push(s=new i(this.O(R()),this.O(R()),this,this.options)):s=e[r],s._$AI(n),r++;r<e.length&&(this._$AR(s&&s._$AB.nextSibling,r),e.length=r)}_$AR(t=this._$AA.nextSibling,e){for(this._$AP?.(!1,!0,e);t!==this._$AB;){let s=lt(t).nextSibling;lt(t).remove(),t=s}}setConnected(t){this._$AM===void 0&&(this._$Cv=t,this._$AP?.(t))}},C=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(t,e,s,r,n){this.type=1,this._$AH=d,this._$AN=void 0,this.element=t,this.name=e,this._$AM=r,this.options=n,s.length>2||s[0]!==""||s[1]!==""?(this._$AH=Array(s.length-1).fill(new String),this.strings=s):this._$AH=d}_$AI(t,e=this,s,r){let n=this.strings,o=!1;if(n===void 0)t=S(this,t,e,0),o=!T(t)||t!==this._$AH&&t!==E,o&&(this._$AH=t);else{let l=t,a,h;for(t=n[0],a=0;a<n.length-1;a++)h=S(this,l[s+a],e,a),h===E&&(h=this._$AH[a]),o||=!T(h)||h!==this._$AH[a],h===d?t=d:t!==d&&(t+=(h??"")+n[a+1]),this._$AH[a]=h}o&&!r&&this.j(t)}j(t){t===d?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,t??"")}},J=class extends C{constructor(){super(...arguments),this.type=3}j(t){this.element[this.name]=t===d?void 0:t}},Y=class extends C{constructor(){super(...arguments),this.type=4}j(t){this.element.toggleAttribute(this.name,!!t&&t!==d)}},G=class extends C{constructor(t,e,s,r,n){super(t,e,s,r,n),this.type=5}_$AI(t,e=this){if((t=S(this,t,e,0)??d)===E)return;let s=this._$AH,r=t===d&&s!==d||t.capture!==s.capture||t.once!==s.once||t.passive!==s.passive,n=t!==d&&(s===d||r);r&&this.element.removeEventListener(this.name,this,s),n&&this.element.addEventListener(this.name,this,t),this._$AH=t}handleEvent(t){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,t):this._$AH.handleEvent(t)}},Q=class{constructor(t,e,s){this.element=t,this.type=6,this._$AN=void 0,this._$AM=e,this.options=s}get _$AU(){return this._$AM._$AU}_$AI(t){S(this,t)}};var Ot=X.litHtmlPolyfillSupport;Ot?.(M,O),(X.litHtmlVersions??=[]).push("3.3.3");var yt=(i,t,e)=>{let s=e?.renderBefore??t,r=s._$litPart$;if(r===void 0){let n=e?.renderBefore??null;s._$litPart$=r=new O(t.insertBefore(R(),n),n,void 0,e??{})}return r._$AI(i),r};var st=globalThis,$=class extends _{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let t=super.createRenderRoot();return this.renderOptions.renderBefore??=t.firstChild,t}update(t){let e=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(t),this._$Do=yt(e,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return E}};$._$litElement$=!0,$.finalized=!0,st.litElementHydrateSupport?.({LitElement:$});var zt=st.litElementPolyfillSupport;zt?.({LitElement:$});(st.litElementVersions??=[]).push("4.2.2");var bt=i=>(t,e)=>{e!==void 0?e.addInitializer(()=>{customElements.define(i,t)}):customElements.define(i,t)};var Nt={attribute:!0,type:String,converter:U,reflect:!1,hasChanged:j},It=(i=Nt,t,e)=>{let{kind:s,metadata:r}=e,n=globalThis.litPropertyMetadata.get(r);if(n===void 0&&globalThis.litPropertyMetadata.set(r,n=new Map),s==="setter"&&((i=Object.create(i)).wrapped=!0),n.set(e.name,i),s==="accessor"){let{name:o}=e;return{set(l){let a=t.get.call(this);t.set.call(this,l),this.requestUpdate(o,a,i,!0,l)},init(l){return l!==void 0&&this.C(o,void 0,i,l),l}}}if(s==="setter"){let{name:o}=e;return function(l){let a=this[o];t.call(this,l),this.requestUpdate(o,a,i,!0,l)}}throw Error("Unsupported decorator location: "+s)};function q(i){return(t,e)=>typeof e=="object"?It(i,t,e):((s,r,n)=>{let o=r.hasOwnProperty(n);return r.constructor.createProperty(n,s),o?Object.getOwnPropertyDescriptor(r,n):void 0})(i,t,e)}function v(i){return q({...i,state:!0,attribute:!1})}var $t={disarmed:"Disarmed",armed_away:"Armed \xB7 Away",armed_home:"Armed \xB7 Home",armed_night:"Armed \xB7 Night",arming:"Arming\u2026",pending:"Entry Delay\u2026",triggered:"ALARM",unavailable:"Unavailable",unknown:"Unknown"},m=class extends ${constructor(){super(...arguments);this._showProgramming=!1;this._showDisarmInput=!1;this._disarmCode="";this._progPartition="1";this._progKeys="";this._progConfirm=!1;this._progError=null}setConfig(e){if(!e.alarm_entity)throw new Error("vista-console-card: `alarm_entity` is required");this._config={show_programming_console:!0,...e}}getCardSize(){return 6}static getStubConfig(){return{alarm_entity:"alarm_control_panel.partition"}}get _entryId(){let e=this.hass?.states[this._config.alarm_entity];return this._config.entry_id??e?.attributes?.config_entry_id}_zoneEntities(){if(!this.hass)return[];if(this._config.zone_entities?.length)return this._config.zone_entities.map(s=>this.hass.states[s]).filter(s=>!!s);let e=this._entryId;return Object.values(this.hass.states).filter(s=>s.entity_id.startsWith("binary_sensor.")&&s.attributes.config_entry_id===e&&s.attributes.zone_number!==void 0)}_troubleEntity(){let e=this._entryId;return Object.values(this.hass.states).find(s=>s.entity_id.startsWith("binary_sensor.")&&s.attributes.config_entry_id===e&&s.attributes.zone_number===void 0)}render(){if(!this.hass||!this._config)return u``;let e=this.hass.states[this._config.alarm_entity];if(!e)return u`<ha-card>
        <div class="warning">Entity ${this._config.alarm_entity} not found.</div>
      </ha-card>`;let s=e.state in $t?e.state:"unknown",r=this._troubleEntity(),n=this._zoneEntities().sort((o,l)=>(o.attributes.zone_number??0)-(l.attributes.zone_number??0));return u`
      <ha-card>
        <div class="console state-${s}">
          <div class="header">
            <div class="title">
              <ha-icon icon="mdi:shield-home"></ha-icon>
              <span>${this._config.title??"Vista Console"}</span>
            </div>
            <div class="conn-dot ${e.state==="unavailable"?"off":"on"}"></div>
          </div>

          ${r?.state==="on"?u`<div class="banner trouble">
                <ha-icon icon="mdi:alert"></ha-icon>
                System trouble condition present
              </div>`:d}

          <div class="status-block">
            <div class="status-label">${$t[s]}</div>
            ${this._renderActions(s)}
          </div>

          ${n.length?u`<div class="zones">
                ${n.map(o=>this._renderZone(o))}
              </div>`:d}

          ${this._config.show_programming_console?this._renderProgrammingConsole():d}
        </div>
      </ha-card>
    `}_renderActions(e){return e==="disarmed"?u`<div class="actions">
        <button class="btn away" @click=${()=>this._arm("away")}>Away</button>
        <button class="btn home" @click=${()=>this._arm("home")}>Home</button>
        <button class="btn night" @click=${()=>this._arm("night")}>Night</button>
      </div>`:u`<div class="actions">
      ${this._showDisarmInput?u`<input
              class="code-input"
              type="password"
              inputmode="numeric"
              placeholder="Code"
              .value=${this._disarmCode}
              @input=${s=>this._disarmCode=s.target.value}
            />
            <button class="btn disarm" @click=${()=>this._disarm()}>Confirm</button>`:u`<button
            class="btn disarm"
            @click=${()=>this._showDisarmInput=!0}
          >
            Disarm
          </button>`}
    </div>`}_renderZone(e){let s=e.state==="on",r=!!e.attributes.bypassed,n=!!e.attributes.fault,o=!!e.attributes.tamper,l=e.attributes.friendly_name??e.entity_id;return u`<div
      class="zone ${s?"open":"closed"} ${r?"bypassed":""} ${n||o?"fault":""}"
      title=${l}
      @click=${()=>this._toggleBypass(e)}
    >
      <ha-icon icon=${s?"mdi:door-open":"mdi:door-closed"}></ha-icon>
      <span class="zone-name">${l}</span>
      ${r?u`<span class="pill">BYPASS</span>`:d}
    </div>`}_renderProgrammingConsole(){return this._showProgramming?u`<div class="programming">
      <div class="banner warning">
        <ha-icon icon="mdi:alert-octagon"></ha-icon>
        Raw keypad sequences. A sequence containing <code>*8</code> enters
        installer programming and can lock the panel out until it is
        power-cycled; installer mode also governs fire-zone and
        UL-listing-relevant settings. Only proceed if you know exactly what
        this sequence does on a Vista panel.
      </div>
      <div class="prog-row">
        <label>Partition</label>
        <input
          class="prog-input small"
          type="number"
          min="1"
          max="8"
          .value=${this._progPartition}
          @input=${e=>this._progPartition=e.target.value}
        />
      </div>
      <div class="prog-row">
        <label>Keys</label>
        <input
          class="prog-input"
          type="text"
          placeholder="e.g. *1 01 #"
          .value=${this._progKeys}
          @input=${e=>this._progKeys=e.target.value}
        />
      </div>
      <label class="confirm-row">
        <input
          type="checkbox"
          .checked=${this._progConfirm}
          @change=${e=>this._progConfirm=e.target.checked}
        />
        I understand the installer-mode / fire-safety risk above.
      </label>
      ${this._progError?u`<div class="banner trouble">${this._progError}</div>`:d}
      <div class="actions">
        <button class="btn away" @click=${()=>this._sendKeystrokes()}>
          Send
        </button>
        <button
          class="btn disarm"
          @click=${()=>this._showProgramming=!1}
        >
          Close
        </button>
      </div>
    </div>`:u`<button
        class="prog-toggle"
        @click=${()=>this._showProgramming=!0}
      >
        <ha-icon icon="mdi:wrench-cog"></ha-icon>
        Advanced Programming Console
      </button>`}async _arm(e){await this.hass.callService("alarm_control_panel",`alarm_arm_${e}`,{entity_id:this._config.alarm_entity})}async _disarm(){await this.hass.callService("alarm_control_panel","alarm_disarm",{entity_id:this._config.alarm_entity,code:this._disarmCode||void 0}),this._disarmCode="",this._showDisarmInput=!1}async _toggleBypass(e){let s=this._entryId;if(!s)return;let r=e.attributes.friendly_name??e.entity_id,n=e.attributes.bypassed?"un-bypass":"bypass";window.confirm(`${n==="bypass"?"Bypass":"Un-bypass"} ${r}?`)&&await this.hass.callService("vista_console","toggle_zone_bypass",{entry_id:s,zone:e.attributes.zone_number})}async _sendKeystrokes(){let e=this._entryId;if(this._progError=null,!e){this._progError="Could not determine the config entry id for this card.";return}if(!this._progKeys.trim()){this._progError="Enter a keystroke sequence first.";return}if(this._progKeys.includes("*8")&&!this._progConfirm){this._progError="This sequence enters installer mode. Check the confirmation box first.";return}try{await this.hass.callService("vista_console","send_keystrokes",{entry_id:e,partition:Number(this._progPartition)||1,keys:this._progKeys,confirm_installer_risk:this._progConfirm}),this._progKeys=""}catch(s){this._progError=s instanceof Error?s.message:String(s)}}};m.styles=W`
    :host {
      --vc-bg: #0f172a;
      --vc-bg-raised: #1e293b;
      --vc-border: #334155;
      --vc-text: #e2e8f0;
      --vc-text-dim: #94a3b8;
      --vc-away: #f59e0b;
      --vc-home: #3b82f6;
      --vc-night: #6366f1;
      --vc-safe: #22c55e;
      --vc-danger: #ef4444;
    }
    ha-card {
      overflow: hidden;
      border-radius: 16px;
    }
    .console {
      background: linear-gradient(160deg, var(--vc-bg), var(--vc-bg-raised));
      color: var(--vc-text);
      padding: 16px 18px 20px;
      font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    }
    .header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 12px;
    }
    .title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 1.05rem;
      font-weight: 600;
      letter-spacing: 0.02em;
    }
    .conn-dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
    }
    .conn-dot.on {
      background: var(--vc-safe);
      box-shadow: 0 0 8px var(--vc-safe);
    }
    .conn-dot.off {
      background: var(--vc-danger);
    }
    .banner {
      display: flex;
      gap: 8px;
      align-items: flex-start;
      border-radius: 10px;
      padding: 8px 12px;
      font-size: 0.85rem;
      margin-bottom: 12px;
      line-height: 1.4;
    }
    .banner.trouble {
      background: rgba(239, 68, 68, 0.15);
      color: #fca5a5;
      border: 1px solid rgba(239, 68, 68, 0.35);
    }
    .banner.warning {
      background: rgba(245, 158, 11, 0.12);
      color: #fcd34d;
      border: 1px solid rgba(245, 158, 11, 0.35);
    }
    .status-block {
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--vc-border);
      border-radius: 12px;
      padding: 16px;
      text-align: center;
      margin-bottom: 14px;
    }
    .status-label {
      font-size: 1.4rem;
      font-weight: 700;
      margin-bottom: 12px;
      letter-spacing: 0.01em;
    }
    .state-armed_away .status-label {
      color: var(--vc-away);
    }
    .state-armed_home .status-label {
      color: var(--vc-home);
    }
    .state-armed_night .status-label {
      color: var(--vc-night);
    }
    .state-disarmed .status-label {
      color: var(--vc-safe);
    }
    .state-triggered .status-label {
      color: var(--vc-danger);
      animation: pulse 1s infinite;
    }
    .state-pending .status-label,
    .state-arming .status-label {
      color: var(--vc-away);
      animation: pulse 1.4s infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.5; }
    }
    .actions {
      display: flex;
      gap: 8px;
      justify-content: center;
      flex-wrap: wrap;
    }
    .btn {
      border: none;
      border-radius: 8px;
      padding: 10px 16px;
      font-size: 0.9rem;
      font-weight: 600;
      cursor: pointer;
      color: #0f172a;
      transition: transform 0.1s ease;
    }
    .btn:active {
      transform: scale(0.96);
    }
    .btn.away { background: var(--vc-away); }
    .btn.home { background: var(--vc-home); color: white; }
    .btn.night { background: var(--vc-night); color: white; }
    .btn.disarm { background: var(--vc-safe); }
    .code-input, .prog-input {
      background: var(--vc-bg);
      border: 1px solid var(--vc-border);
      color: var(--vc-text);
      border-radius: 8px;
      padding: 9px 10px;
      font-size: 0.9rem;
    }
    .prog-input.small {
      width: 60px;
    }
    .zones {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
      gap: 8px;
      margin-bottom: 14px;
    }
    .zone {
      display: flex;
      align-items: center;
      gap: 6px;
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--vc-border);
      border-radius: 10px;
      padding: 8px 10px;
      cursor: pointer;
      font-size: 0.82rem;
      transition: border-color 0.15s ease;
    }
    .zone:hover {
      border-color: var(--vc-home);
    }
    .zone.open {
      color: var(--vc-away);
    }
    .zone.closed {
      color: var(--vc-text-dim);
    }
    .zone.fault {
      border-color: var(--vc-danger);
      color: var(--vc-danger);
    }
    .zone-name {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .pill {
      margin-left: auto;
      background: var(--vc-away);
      color: #0f172a;
      font-size: 0.65rem;
      font-weight: 700;
      border-radius: 6px;
      padding: 2px 5px;
    }
    .prog-toggle {
      width: 100%;
      background: transparent;
      border: 1px dashed var(--vc-border);
      color: var(--vc-text-dim);
      border-radius: 10px;
      padding: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      cursor: pointer;
      font-size: 0.85rem;
    }
    .programming {
      border: 1px solid var(--vc-border);
      border-radius: 12px;
      padding: 12px;
      background: rgba(0, 0, 0, 0.15);
    }
    .prog-row {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 10px;
    }
    .prog-row label {
      width: 70px;
      font-size: 0.85rem;
      color: var(--vc-text-dim);
    }
    .confirm-row {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 0.8rem;
      color: var(--vc-text-dim);
      margin-bottom: 10px;
    }
    .warning {
      padding: 16px;
      color: var(--vc-danger);
    }
  `,g([q({attribute:!1})],m.prototype,"hass",2),g([v()],m.prototype,"_config",2),g([v()],m.prototype,"_showProgramming",2),g([v()],m.prototype,"_showDisarmInput",2),g([v()],m.prototype,"_disarmCode",2),g([v()],m.prototype,"_progPartition",2),g([v()],m.prototype,"_progKeys",2),g([v()],m.prototype,"_progConfirm",2),g([v()],m.prototype,"_progError",2),m=g([bt("vista-console-card")],m);window.customCards=window.customCards||[];window.customCards.push({type:"vista-console-card",name:"Vista Console Card",description:"Modern control + programming console for a Vista panel bridged via Envisalink."});export{m as VistaConsoleCard};
