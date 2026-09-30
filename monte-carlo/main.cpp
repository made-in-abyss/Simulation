#include <bits/stdc++.h>

using namespace std;
double drift,vol,s0;

vector<double>sim;
void monte(){
    random_device rd;
    mt19937 gen(rd());
    student_t_distribution<double> shock(4.0);
    double price = s0;
    for(int i = 1;i<=1000;i++){
        if ((double)rand() / RAND_MAX < 0.05) {
            drift*=-1;
        }
        double rate = exp((drift-(vol*vol)/2)+vol*shock(gen));
        price*=rate;
        sim.push_back(price);
    }
}

int main()
{
    int n;
    cin>>drift>>vol>>s0;
    monte();
    for(double i:sim)cout<<i<<" ";
}
