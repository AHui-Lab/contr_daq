clear;
clc;
loadlibrary('NET_AMC4XER','NET_AMC4XER.h');
 
x=calllib('NET_AMC4XER','SOCKET_init');
%使能X运动轴
% Set_Axs(char* destIP,unsigned int Axs,unsigned int Run_EN,unsigned int Csta_EN,unsigned int Cstp_EN,unsigned int Csd_EN);
 x=calllib('NET_AMC4XER','Set_Axs','192.168.1.30',0,1,0,0,0);
% X运动轴定长运动
%DeltMov_V6043S2X(char* destIP,unsigned int Axs,unsigned int curve,unsigned int Dir,unsigned char Outmod,unsigned int Vo,unsigned int Vt,unsigned int Length,unsigned int StartDec,unsigned int Acctime,unsigned int Dectime,unsigned int SD_EN,unsigned int WaitSYNC);
x=calllib('NET_AMC4XER','DeltMov','192.168.1.30',0,1,0,0,1000,20000,30000,0,200,200,0,0);   

%停止X运动轴
%x=calllib('NET_AMC4XER','AxsStop','192.168.1.30',0); %AxsStop(char* destIP,unsigned int Axs);
calllib('NET_AMC4XER','SOCKET_delete');
  unloadlibrary( 'NET_AMC4XER');