#include <bits/stdc++.h>

using namespace std;
double drift,vol,s0;

double sim[1005];
void monte(){
    random_device rd;
    mt19937 gen(rd());
    student_t_distribution<double> shock(4.0);
    uniform_real_distribution<double> regime(0.0,1.0);
    double scale = sqrt((4.0-2.0)/4.0);
    double price = s0;
    for(int i = 1;i<=1000;i++){
        if (regime(gen) <= 0.05)drift *= -1;
        double rate = exp(drift+vol*scale*shock(gen));
        price*=rate;
        sim[i] = price;
    }
}
int main()
{
    int n;
    cin>>n>>drift>>vol>>s0;
    vector<double>end_price;
    vector<double>draw;
    vector<double>price_step[1005];
    vector<double>one;vector<double>two;vector<double>three;
    for(int i =  1;i<=n;i++){
        monte();
        double peak = 0.0;
        double drawdown = 0.0;
        for(int j = 1;j<=1000;j++){
            price_step[j].push_back(sim[j]);
            peak = max(peak,sim[j]);
            drawdown = min(drawdown,((sim[j]-peak)/peak));
        }
        end_price.push_back(sim[1000]);
        draw.push_back(drawdown);
    }
    sort(end_price.begin(),end_price.end());
    sort(draw.begin(),draw.end());
    for(int i =1;i<=1000;i++){
        sort(price_step[i].begin(),price_step[i].end());
        one.push_back(price_step[i][int(n*0.1)]);
        two.push_back(price_step[i][int(n*0.5)]);
        three.push_back(price_step[i][int(n*0.9)]);
    }
    for(auto i:one)cout<<i<<" ";
    cout<<"\n";
    for(auto i:two)cout<<i<<" ";
    cout<<"\n";
    for(auto i:three)cout<<i<<" ";
    cout<<"\n";
    cout<<end_price[int(n*0.1)]<<" "<<draw[int(n*0.1)];
}
